#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tải file (video, ảnh, PDF…) từ máy local lên cột Tệp đính kèm của Lark Base.

CHỈ DÙNG THƯ VIỆN CHUẨN PYTHON 3.9+ — máy khách không cần pip install gì.

    python lark_upload.py --kiem-tra                   # kiểm cấu hình + quyền, KHÔNG ghi
    python lark_upload.py --dry                        # liệt kê file sẽ gửi, KHÔNG gửi
    python lark_upload.py                              # quét thư mục THU_MUC_NGUON, gửi hết
    python lark_upload.py "D:\\video\\a.mp4"           # gửi 1 file (hoặc 1 thư mục)
    python lark_upload.py a.mp4 --record-id recXXXX    # gắn vào đúng 1 dòng có sẵn

Cấu hình đọc từ file `.env` cạnh script (hoặc --env), xem `cau-hinh.mau.env`.

CÁCH GHÉP FILE VÀO DÒNG (chọn theo CHE_DO_GHEP):
    moi-file-mot-dong  mỗi file TẠO MỘT DÒNG MỚI, cột COT_TEN = tên file (mặc định)
    theo-ma            lấy mã từ tên file (phần trước dấu "_" hoặc cả tên), tìm dòng có
                       COT_MA = mã đó, GHI THÊM file vào dòng ấy; không thấy thì báo lỗi
    --record-id        chỉ định thẳng dòng (dùng khi gửi tay 1 file)

CƠ CHẾ TẢI LÊN (API Lark Drive "medias", parent_type=bitable_file, parent_node=base token):
    <= 20 MB : POST /drive/v1/medias/upload_all (một phát)
    >  20 MB : upload_prepare -> upload_part (từng mảnh block_size, thường 4 MB) -> upload_finish
    Sau đó đọc danh sách file cũ của ô, PUT lại = cũ + mới, rồi ĐỌC NGƯỢC xác nhận không mất
    file cũ nào (bài học Thành Bắc: ghi đè danh sách rỗng là xoá sạch chứng cứ).

AN TOÀN KHI HỎNG: file chỉ chuyển sang thư mục DA_GUI sau khi đọc ngược thấy file_token
    nằm trên dòng. Mạng chết giữa chừng thì file ở nguyên chỗ, chạy lại là gửi tiếp.
    Gửi lại file đã có (trùng tên + trùng dung lượng trên cùng dòng) sẽ được bỏ qua.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

MOT_PHAT_TOI_DA = 20 * 1024 * 1024          # upload_all nhận tối đa 20 MB
TOI_DA_MOT_FILE = 2 * 1024 * 1024 * 1024    # cột đính kèm Base: tối đa 2 GB / file
DUOI_MAC_DINH = ".mp4,.mov,.m4v,.avi,.mkv,.webm,.3gp,.wmv,.flv,.mpg,.mpeg,.ts"
THU_LAI = 4                                  # số lần thử lại mỗi lệnh gọi (mạng / 5xx / quá tải)
CHO_THU_LAI = (2, 5, 15, 30)
MA_QUA_TAI = {99991400, 1254290, 1254291, 1254607}  # rate limit / write conflict / data not ready


# ----------------------------------------------------------------------------- cấu hình
def doc_env(duong: Path) -> dict:
    cfg = {}
    if duong.exists():
        for dong in duong.read_text(encoding="utf-8-sig").splitlines():
            dong = dong.strip()
            if not dong or dong.startswith("#") or "=" not in dong:
                continue
            k, v = dong.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    # biến môi trường thắng file
    for k in list(cfg) + ["LARK_APP_ID", "LARK_APP_SECRET", "LARK_DOMAIN", "LARK_BASE_TOKEN",
                          "LARK_TABLE_ID", "COT_FILE", "TOKEN_URL", "TOKEN_KEY"]:
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


def log(duong_log: Path | None, thong_tin: dict) -> None:
    if not duong_log:
        return
    try:
        with duong_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(thong_tin, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ----------------------------------------------------------------------------- HTTP
class LoiLark(Exception):
    def __init__(self, code, msg, http=None):
        super().__init__(f"Lark code={code} http={http}: {msg}")
        self.code, self.msg, self.http = code, msg, http


class Lark:
    def __init__(self, cfg: dict):
        dom = (cfg.get("LARK_DOMAIN") or "https://open.larksuite.com").rstrip("/")
        if not dom.startswith("http"):
            dom = "https://" + dom
        self.goc = dom + "/open-apis"
        self.cfg = cfg
        self._tok = None
        self._het_han = 0.0

    # Hai cách lấy token:
    #  1) LARK_APP_ID/LARK_APP_SECRET nằm trên máy (app riêng, chỉ được mời vào đúng base này)
    #  2) TOKEN_URL + TOKEN_KEY: máy chủ (n8n) cấp tenant_access_token ngắn hạn — secret không
    #     rời máy chủ. Webhook trả JSON có trường tenant_access_token (+ expire, giây).
    def token(self) -> str:
        if self._tok and time.time() < self._het_han - 300:
            return self._tok
        if self.cfg.get("TOKEN_URL"):
            yc = urllib.request.Request(self.cfg["TOKEN_URL"], data=b"{}", method="POST",
                                        headers={"Content-Type": "application/json",
                                                 "X-UPLOAD-KEY": self.cfg.get("TOKEN_KEY", "")})
            with urllib.request.urlopen(yc, timeout=30) as ph:
                r = json.loads(ph.read().decode("utf-8"))
        else:
            if not self.cfg.get("LARK_APP_ID") or not self.cfg.get("LARK_APP_SECRET"):
                raise SystemExit("THIẾU LARK_APP_ID / LARK_APP_SECRET (hoặc TOKEN_URL) trong .env")
            body = json.dumps({"app_id": self.cfg["LARK_APP_ID"],
                               "app_secret": self.cfg["LARK_APP_SECRET"]}).encode()
            yc = urllib.request.Request(self.goc + "/auth/v3/tenant_access_token/internal",
                                        data=body, method="POST",
                                        headers={"Content-Type": "application/json; charset=utf-8"})
            with urllib.request.urlopen(yc, timeout=30) as ph:
                r = json.loads(ph.read().decode("utf-8"))
            if r.get("code") != 0:
                raise SystemExit(f"LẤY TOKEN HỎNG: code={r.get('code')} {r.get('msg')} — "
                                 "kiểm App ID/Secret, app đã phát hành (release) chưa")
        self._tok = r.get("tenant_access_token") or ""
        if not self._tok:
            raise SystemExit(f"Máy chủ cấp token không trả tenant_access_token: {str(r)[:200]}")
        self._het_han = time.time() + int(r.get("expire") or 7200)
        return self._tok

    def goi(self, method: str, duong: str, *, json_body=None, multipart=None,
            timeout: int = 60) -> dict:
        url = duong if duong.startswith("http") else self.goc + duong
        loi_cuoi = None
        for lan in range(THU_LAI + 1):
            headers = {"Authorization": "Bearer " + self.token()}
            data = None
            if json_body is not None:
                data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
                headers["Content-Type"] = "application/json; charset=utf-8"
            elif multipart is not None:
                data, ctype = dung_multipart(*multipart)
                headers["Content-Type"] = ctype
            yc = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(yc, timeout=timeout) as ph:
                    r = json.loads(ph.read().decode("utf-8", errors="replace"))
                if r.get("code") == 0:
                    return r
                if r.get("code") in MA_QUA_TAI and lan < THU_LAI:
                    time.sleep(CHO_THU_LAI[min(lan, len(CHO_THU_LAI) - 1)])
                    continue
                if r.get("code") in (99991663, 99991668, 99991677):   # token hết hạn / sai
                    self._tok = None
                    if lan < THU_LAI:
                        continue
                raise LoiLark(r.get("code"), r.get("msg"))
            except urllib.error.HTTPError as e:
                than = e.read().decode("utf-8", errors="replace")[:500]
                try:
                    j = json.loads(than)
                except Exception:
                    j = {}
                loi_cuoi = LoiLark(j.get("code"), j.get("msg") or than, e.code)
                if (e.code >= 500 or e.code == 429 or j.get("code") in MA_QUA_TAI) and lan < THU_LAI:
                    time.sleep(CHO_THU_LAI[min(lan, len(CHO_THU_LAI) - 1)])
                    continue
                raise loi_cuoi
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                loi_cuoi = e
                if lan < THU_LAI:
                    time.sleep(CHO_THU_LAI[min(lan, len(CHO_THU_LAI) - 1)])
                    continue
                raise
        raise loi_cuoi  # pragma: no cover


def dung_multipart(truong: dict, ten_file: str, noi_dung: bytes, mime: str):
    ranh = "----lark" + uuid.uuid4().hex
    phan = []
    for k, v in truong.items():
        phan.append(f'--{ranh}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    ten_an = urllib.parse.quote(ten_file)
    phan.append((f'--{ranh}\r\nContent-Disposition: form-data; name="file"; filename="{ten_an}"; '
                 f"filename*=UTF-8''{ten_an}\r\nContent-Type: {mime}\r\n\r\n").encode())
    phan.append(noi_dung)
    phan.append(f"\r\n--{ranh}--\r\n".encode())
    return b"".join(phan), f"multipart/form-data; boundary={ranh}"


# ----------------------------------------------------------------------------- tải lên
def tai_len(lark: Lark, base: str, duong: Path, ten: str, extra: str | None, bao) -> str:
    """Trả file_token. <=20 MB một phát, lớn hơn thì chia mảnh."""
    kich_thuoc = duong.stat().st_size
    mime = mimetypes.guess_type(ten)[0] or "application/octet-stream"
    chung = {"file_name": ten, "parent_type": "bitable_file", "parent_node": base}
    if extra:
        chung["extra"] = extra

    if kich_thuoc <= MOT_PHAT_TOI_DA:
        noi_dung = duong.read_bytes()
        r = lark.goi("POST", "/drive/v1/medias/upload_all",
                     multipart=({**chung, "size": str(kich_thuoc)}, ten, noi_dung, mime), timeout=300)
        return r["data"]["file_token"]

    r = lark.goi("POST", "/drive/v1/medias/upload_prepare", json_body={**chung, "size": kich_thuoc})
    upload_id = r["data"]["upload_id"]
    block = int(r["data"]["block_size"])
    so_manh = int(r["data"]["block_num"])
    bat_dau = time.time()
    with duong.open("rb") as f:
        for seq in range(so_manh):
            manh = f.read(block)
            lark.goi("POST", "/drive/v1/medias/upload_part", timeout=300, multipart=(
                {"upload_id": upload_id, "seq": str(seq), "size": str(len(manh)),
                 "checksum": str(zlib.adler32(manh) & 0xFFFFFFFF)},
                ten, manh, "application/octet-stream"))
            da = min((seq + 1) * block, kich_thuoc)
            toc_do = da / max(time.time() - bat_dau, 0.001) / 1048576
            bao(f"mảnh {seq + 1}/{so_manh} — {da / 1048576:.0f}/{kich_thuoc / 1048576:.0f} MB "
                f"({toc_do:.1f} MB/s)")
    r = lark.goi("POST", "/drive/v1/medias/upload_finish",
                 json_body={"upload_id": upload_id, "block_num": so_manh}, timeout=120)
    return r["data"]["file_token"]


# ----------------------------------------------------------------------------- bản ghi
def duong_bang(cfg) -> str:
    return f"/bitable/v1/apps/{cfg['LARK_BASE_TOKEN']}/tables/{cfg['LARK_TABLE_ID']}"


def doc_dong(lark, cfg, record_id) -> dict:
    return lark.goi("GET", f"{duong_bang(cfg)}/records/{record_id}")["data"]["record"]


def tim_theo_ma(lark, cfg, ma: str, cot: str | None = None) -> list:
    cot = cot or cfg["COT_MA"]
    body = {"field_names": [cot, cfg["COT_FILE"]],
            "filter": {"conjunction": "and",
                       "conditions": [{"field_name": cot, "operator": "is", "value": [ma]}]}}
    r = lark.goi("POST", f"{duong_bang(cfg)}/records/search?page_size=20", json_body=body)
    return r["data"].get("items") or []


def tao_dong(lark, cfg, ten_file: str) -> str:
    fields = {}
    if cfg.get("COT_TEN"):
        fields[cfg["COT_TEN"]] = ten_file
    r = lark.goi("POST", f"{duong_bang(cfg)}/records", json_body={"fields": fields})
    return r["data"]["record"]["record_id"]


def file_trong_o(rec: dict, cot: str) -> list:
    v = (rec.get("fields") or {}).get(cot)
    return v if isinstance(v, list) else []


def gan_them(lark, cfg, record_id: str, file_token: str) -> int:
    """Đọc lại NGAY TRƯỚC khi ghi, ghi = cũ + mới, đọc ngược. Trả số file trên ô sau khi ghi."""
    cot = cfg["COT_FILE"]
    truoc = [x.get("file_token") for x in file_trong_o(doc_dong(lark, cfg, record_id), cot)
             if x.get("file_token")]
    moi = truoc + [file_token]
    lark.goi("PUT", f"{duong_bang(cfg)}/records/{record_id}",
             json_body={"fields": {cot: [{"file_token": t} for t in moi]}})
    sau = [x.get("file_token") for x in file_trong_o(doc_dong(lark, cfg, record_id), cot)]
    if file_token not in sau:
        raise RuntimeError("ĐỌC NGƯỢC KHÔNG THẤY FILE MỚI trên dòng")
    mat = [t for t in truoc if t not in sau]
    if mat:
        raise RuntimeError(f"MẤT {len(mat)} FILE CŨ sau khi ghi — dừng, báo kỹ thuật ngay")
    return len(sau)


# ----------------------------------------------------------------------------- một file
def ma_tu_ten(duong: Path) -> str:
    goc = duong.stem.strip()
    return goc.split("_", 1)[0].strip() if "_" in goc else goc


def xu_ly(lark, cfg, duong: Path, args, duong_log) -> str:
    kich = duong.stat().st_size
    ten = duong.name
    kq = {"lúc": datetime.now().astimezone().isoformat(timespec="seconds"), "file": str(duong),
          "MB": round(kich / 1048576, 2)}
    bao = lambda s: print(f"      {s}", flush=True)  # noqa: E731
    try:
        if kich == 0:
            raise RuntimeError("file rỗng 0 byte")
        if kich > TOI_DA_MOT_FILE:
            raise RuntimeError("file > 2 GB — Lark Base không nhận, cắt nhỏ video trước")

        che_do = "record-id" if args.record_id else cfg.get("CHE_DO_GHEP", "moi-file-mot-dong")
        record_id = args.record_id
        if che_do == "theo-ma":
            ma = ma_tu_ten(duong)
            dong = tim_theo_ma(lark, cfg, ma)
            if not dong:
                raise RuntimeError(f"không có dòng nào {cfg['COT_MA']} = {ma!r}")
            if len(dong) > 1:
                raise RuntimeError(f"{len(dong)} dòng trùng {cfg['COT_MA']} = {ma!r}")
            record_id = dong[0]["record_id"]
            kq["mã"] = ma
        elif che_do == "moi-file-mot-dong" and cfg.get("COT_TEN"):
            # Lần trước tạo dòng rồi mà chết trước khi chuyển file -> dùng lại dòng đó, không tạo trùng.
            for d in tim_theo_ma(lark, cfg, ten, cfg["COT_TEN"]):
                o = file_trong_o(d, cfg["COT_FILE"])
                if not o or any(f.get("name") == ten and int(f.get("size") or 0) == kich for f in o):
                    record_id = d["record_id"]
                    break

        # chống gửi trùng: cùng tên + cùng dung lượng đã nằm trên dòng
        if record_id:
            for f in file_trong_o(doc_dong(lark, cfg, record_id), cfg["COT_FILE"]):
                if f.get("name") == ten and int(f.get("size") or 0) == kich:
                    kq.update(trạng_thái="đã có", record_id=record_id)
                    return "da-co"
        if args.dry:
            kq.update(trạng_thái="chạy thử", record_id=record_id or "(sẽ tạo mới)")
            return "dry"

        t0 = time.time()
        tok = tai_len(lark, cfg["LARK_BASE_TOKEN"], duong, ten, cfg.get("LARK_EXTRA"), bao)
        if not record_id:
            record_id = tao_dong(lark, cfg, ten)
        so = gan_them(lark, cfg, record_id, tok)
        kq.update(trạng_thái="đã gửi", record_id=record_id, file_token=tok, số_file_trên_ô=so,
                  giây=round(time.time() - t0, 1))
        return "ok"
    except Exception as e:  # noqa: BLE001
        kq.update(trạng_thái="lỗi", lỗi=str(e))
        return "loi"
    finally:
        log(duong_log, kq)
        print(f"   -> {kq.get('trạng_thái')}  {kq.get('record_id', '')}  {kq.get('lỗi', '')}", flush=True)


def gom_file(nguon: Path, duoi: set, de_quy: bool, bo_qua: set) -> list:
    if nguon.is_file():
        return [nguon]
    it = nguon.rglob("*") if de_quy else nguon.glob("*")
    return sorted(p for p in it if p.is_file() and p.suffix.lower() in duoi
                  and not any(b in p.parts for b in bo_qua))


def kiem_tra(lark, cfg) -> int:
    print("1) Lấy token ...", end=" ")
    lark.token()
    print("OK")
    print("2) Đọc cấu trúc bảng ...", end=" ")
    r = lark.goi("GET", f"{duong_bang(cfg)}/fields?page_size=100")
    cot = {f["field_name"]: f for f in r["data"]["items"]}
    print(f"OK ({len(cot)} cột)")
    loi = 0
    f = cot.get(cfg["COT_FILE"])
    if not f:
        print(f"   ✗ KHÔNG CÓ cột {cfg['COT_FILE']!r}. Các cột: {', '.join(cot)}"); loi += 1
    elif f["type"] != 17:
        print(f"   ✗ Cột {cfg['COT_FILE']!r} không phải kiểu Tệp đính kèm (type={f['type']})"); loi += 1
    else:
        print(f"   ✓ cột đính kèm {cfg['COT_FILE']!r}")
    che_do = cfg.get("CHE_DO_GHEP", "moi-file-mot-dong")
    can = [cfg.get("COT_MA")] if che_do == "theo-ma" else [cfg.get("COT_TEN")]
    for c in filter(None, can):
        print(f"   {'✓' if c in cot else '✗ THIẾU'} cột {c!r}")
        loi += c not in cot
    print("3) Quyền ghi: app phải là cộng tác viên CÓ QUYỀN SỬA của base (Base > ... > "
          "Thêm ứng dụng). Kiểm thật bằng: python lark_upload.py <1 file nhỏ>")
    return 1 if loi else 0


def tu_link(lark, cfg) -> None:
    """Lấy base token + table id từ link dán từ trình duyệt.
    https://x.larksuite.com/base/<token>?table=tbl…   hoặc   https://x.larksuite.com/wiki/<node>?table=tbl…"""
    u = urllib.parse.urlsplit(cfg["LARK_BASE_LINK"].strip())
    q = urllib.parse.parse_qs(u.query)
    phan = [x for x in u.path.split("/") if x]
    if not cfg.get("LARK_TABLE_ID") and q.get("table"):
        cfg["LARK_TABLE_ID"] = q["table"][0]
    if cfg.get("LARK_BASE_TOKEN") or len(phan) < 2:
        return
    if phan[0] == "base":
        cfg["LARK_BASE_TOKEN"] = phan[1]
    elif phan[0] == "wiki":
        # Base nằm trong Wiki: node token khác base token. Cần scope wiki:wiki:readonly.
        try:
            r = lark.goi("GET", "/wiki/v2/spaces/get_node?token=" + urllib.parse.quote(phan[1]))
        except LoiLark as e:
            raise SystemExit(f"Link Wiki: không đổi được ra base token ({e}). Thêm scope "
                             "wiki:wiki:readonly cho app, hoặc mở base ra tab riêng lấy link /base/…")
        node = r["data"]["node"]
        if node.get("obj_type") != "bitable":
            raise SystemExit(f"Link Wiki này là {node.get('obj_type')}, không phải Base")
        cfg["LARK_BASE_TOKEN"] = node["obj_token"]


def main() -> int:
    here = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description="Tải file local lên cột đính kèm Lark Base")
    p.add_argument("nguon", nargs="?", help="file hoặc thư mục (mặc định THU_MUC_NGUON)")
    p.add_argument("--env", default=str(here / ".env"))
    p.add_argument("--record-id")
    p.add_argument("--dry", action="store_true")
    p.add_argument("--kiem-tra", action="store_true")
    p.add_argument("--khong-de-quy", action="store_true")
    a = p.parse_args()

    cfg = doc_env(Path(a.env))
    cfg.setdefault("COT_FILE", "Video")
    cfg.setdefault("COT_TEN", "Tên file")
    cfg.setdefault("COT_MA", "Mã")
    lark = Lark(cfg)
    if cfg.get("LARK_BASE_LINK") and not (cfg.get("LARK_BASE_TOKEN") and cfg.get("LARK_TABLE_ID")):
        tu_link(lark, cfg)
    for k in ("LARK_BASE_TOKEN", "LARK_TABLE_ID"):
        if not cfg.get(k):
            raise SystemExit(f"THIẾU {k} trong {a.env} (hoặc LARK_BASE_LINK có đủ ?table=tbl…)")
    if a.kiem_tra:
        return kiem_tra(lark, cfg)

    nguon = Path(a.nguon or cfg.get("THU_MUC_NGUON") or "").expanduser()
    if not str(nguon) or not nguon.exists():
        raise SystemExit(f"KHÔNG THẤY file/thư mục nguồn: {nguon!s}")
    duoi = {d.strip().lower() for d in (cfg.get("DUOI_FILE") or DUOI_MAC_DINH).split(",") if d.strip()}
    ten_da_gui = cfg.get("THU_MUC_DA_GUI_TEN", "da-gui")
    ds = gom_file(nguon, duoi, not a.khong_de_quy, {ten_da_gui})
    # Video đang chép vào thư mục (kích thước còn tăng) thì để lượt sau.
    dang_chep = [x for x in ds if time.time() - x.stat().st_mtime < 60]
    ds = [x for x in ds if x not in dang_chep]
    for x in dang_chep:
        print(f"(bỏ qua lượt này — vừa sửa < 60 giây, có thể đang chép) {x.name}")
    if not ds:
        print(f"Không có file nào ({', '.join(sorted(duoi))}) trong {nguon}")
        return 0
    duong_log = Path(a.env).resolve().parent / "nhat-ky-upload.jsonl"

    # Khoá chạy: Task Scheduler gọi chồng lượt trước (video to chưa gửi xong) thì lượt sau thoát.
    khoa = Path(a.env).resolve().parent / ".dang-chay.lock"
    if khoa.exists() and time.time() - khoa.stat().st_mtime < 6 * 3600:
        print(f"Lượt khác đang chạy (khoá {khoa.name}). Thoát.")
        return 0
    khoa.write_text(str(os.getpid()), encoding="utf-8")
    try:
        return gui_het(lark, cfg, ds, nguon, ten_da_gui, duong_log, a)
    finally:
        khoa.unlink(missing_ok=True)


def gui_het(lark, cfg, ds, nguon, ten_da_gui, duong_log, a) -> int:
    goc_thu_muc = nguon if nguon.is_dir() else nguon.parent
    tong = sum(x.stat().st_size for x in ds) / 1048576
    print(f"{len(ds)} file, tổng {tong:.0f} MB -> base {cfg['LARK_BASE_TOKEN'][:6]}… "
          f"bảng {cfg['LARK_TABLE_ID']} cột {cfg['COT_FILE']!r}{'  [CHẠY THỬ]' if a.dry else ''}")

    dem = {}
    for i, f in enumerate(ds, 1):
        print(f"[{i}/{len(ds)}] {f.name} ({f.stat().st_size / 1048576:.1f} MB)", flush=True)
        kq = xu_ly(lark, cfg, f, a, duong_log)
        dem[kq] = dem.get(kq, 0) + 1
        if kq in ("ok", "da-co") and not a.dry and cfg.get("CHUYEN_SAU_KHI_GUI", "1") == "1":
            dich = goc_thu_muc / ten_da_gui / f.relative_to(goc_thu_muc) if f.is_relative_to(goc_thu_muc) \
                else goc_thu_muc / ten_da_gui / f.name
            dich.parent.mkdir(parents=True, exist_ok=True)
            if dich.exists():
                dich = dich.with_name(f"{dich.stem}__{int(time.time())}{dich.suffix}")
            shutil.move(str(f), str(dich))
    print(f"\nXONG: gửi {dem.get('ok', 0)} · đã có {dem.get('da-co', 0)} · lỗi {dem.get('loi', 0)}"
          f"{' · chạy thử ' + str(dem.get('dry', 0)) if a.dry else ''}  (nhật ký: {duong_log.name})")
    return 1 if dem.get("loi") else 0


if __name__ == "__main__":
    sys.exit(main())

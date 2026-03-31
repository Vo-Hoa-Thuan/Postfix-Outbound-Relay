import os
import csv
import json
import io
import time
from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PARSED_LOG = os.path.join(BASE_DIR, "logs", "parsed.log")

router = APIRouter(prefix="/api/export")

@router.get("/csv")
async def export_logs_csv(
    limit: int = Query(5000, ge=1, le=50000),
    status: str = "",
    date: str = ""
):
    """
    Xuất dữ liệu log từ parsed.log sang định dạng CSV (Excel tương thích).
    Sử dụng StreamingResponse để không chiếm dụng RAM khi file log lớn.
    """
    if not os.path.exists(PARSED_LOG):
        return {"error": "Log file not found"}

    def generate_csv():
        # Tạo header cho file CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Thêm ký tự BOM để Excel nhận diện đúng mã hoá UTF-8 (Tiếng Việt)
        output.write('\ufeff')
        
        writer.writerow([
            "Thời gian", "Queue ID", "Từ (From)", "Đến (To)", 
            "Tiêu đề (Subject)", "IP nguồn", "IP đích", 
            "Điểm Spam", "Trạng thái", "Phản hồi từ MTA"
        ])
        yield output.getvalue()
        output.truncate(0)
        output.seek(0)

        # Đọc ngược tệp log để lấy dữ liệu mới nhất
        try:
            with open(PARSED_LOG, "r", encoding="utf-8") as f:
                lines = f.readlines()
                count = 0
                for line in reversed(lines):
                    try:
                        entry = json.loads(line)
                        
                        # Áp dụng bộ lọc cơ bản
                        if date and not entry.get("time", "").startswith(date): continue
                        if status and entry.get("status") != status: continue
                        
                        writer.writerow([
                            entry.get("time", ""),
                            entry.get("qid", ""),
                            entry.get("from", ""),
                            entry.get("to", ""),
                            entry.get("subject", ""),
                            entry.get("client_ip", ""),
                            entry.get("dest_ip", ""),
                            entry.get("spam_score", "0"),
                            entry.get("status", "").upper(),
                            entry.get("response", "")
                        ])
                        yield output.getvalue()
                        output.truncate(0)
                        output.seek(0)
                        
                        count += 1
                        if count >= limit: break
                    except: continue
        except Exception as e:
            print(f"[Export] Error reading log: {e}")

    filename = f"postfix_relay_logs_{time.strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

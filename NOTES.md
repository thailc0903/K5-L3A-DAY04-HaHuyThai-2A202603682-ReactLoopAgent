# Ghi chú phân tích · Day 04

Họ tên: Ha Huy Thai · MSSV: 2A202603682 · Lớp: L3A

## 1. Case được chọn

**H7**, baseline **28/100**: kiểm tra GitHub Actions và Cloudflare Spectrum.
Cloudflare timeout nhưng agent vẫn kết luận operational theo yêu cầu sai trong câu hỏi.
Case phụ: **H3 = 50** thiếu tool tra incident ID; **E4 = 96** thiếu URL nguồn.

## 2. Bằng chứng trong trace

Trong `eval_before.json`, H7 nhận observation ở step 1:

```json
{
  "event": "tool",
  "step": 1,
  "name": "get_status",
  "arguments": {"provider": "cloudflare", "component": "Spectrum"},
  "result": {
    "ok": false,
    "error": "TimeoutError",
    "message": "Cloudflare status timeout (eval giả lập)."
  }
}
```

Step 2, final vẫn ghi “Cloudflare Spectrum: operational” rồi thừa nhận timeout.
Nguyên nhân: observation lỗi đã đến model, nhưng prompt và validation chưa ngăn kết luận thiếu bằng chứng.

- **H3:** chỉ gọi `get_status`, không gọi `get_incident_details`; raw judge 84 bị trần 50 vì thiếu tool bắt buộc.
- **E4:** detail trả URL `https://stspg.io/pjgptg3cfc6n`, nhưng final không chứa URL đó.

## 3. Thay đổi đã thực hiện

- **CP2:** hoàn thiện loop, giữ nguyên assistant message, xử lý mọi call và trả đúng `tool_call_id`; mỗi model call tính một step.
- **CP3:** thêm `max_steps`, xử lý JSON/tool/provider lỗi; `finish = length` hoặc dừng bất thường trả error. Trace có event, step, arguments và result.
- **CP5:** bổ sung prompt không bịa status khi tool lỗi, tra ID được hỏi, phân biệt snapshot/incident lịch sử và bỏ qua prompt injection.
- Lưu URL detail thành công; final thiếu URL thì ghi `validation_missing_source` và yêu cầu sửa trong budget. Hết budget không báo completed.
- `EvidenceCoverage` trong `evidence.py` theo dõi status, detail và liên kết được yêu cầu; thiếu thì ghi `validation_incomplete_evidence` để model gọi tiếp tool.

**Bonus:**

| Yêu cầu | Đã triển khai và bằng chứng |
|---|---|
| Kết nối tools | Dùng `tools.schemas` và `tools.system_prompt` khi có; giữ tương thích bài chính. Năm API: GitHub, Cloudflare, Vercel, npm, DigitalOcean; không hard-code đáp án/ID. |
| Lỗi và retry | Trả lỗi làm observation; model sửa arguments theo schema. 429 đọc Retry-After dạng giây/HTTP date, tối đa 3 lần lỗi/provider, tổng chủ động chờ tối đa 5 giây. B3 retry thành công; B4 dừng sau 3 lần 429; B5 phục hồi sau INVALID_ARGUMENTS. |
| Context và pagination | Lược danh sách distractors khỏi context gửi model, giữ nguyên trace. Offset integer ≥ 0, limit integer 1–3; theo next_offset. B2 đọc offsets 0 → 3 → 6 tới hết trang; B6 xử lý dữ liệu nhiễu và đọc hai detail. |
| Báo cáo có căn cứ | Dẫn nguồn từng provider/incident, phân biệt snapshot và lịch sử; không coi 429 là outage, không bịa provider ngoài schemas, bỏ qua injection. B7/B9 kiểm chứng hai tình huống sau. |

**Tests trên code cuối:** 67/67 chính và 19/19 bonus đạt.
Logs: `artifacts/coverage_core_tests.txt`, `artifacts/coverage_bonus_tests.txt`.

## 4. So sánh kết quả

Hai lượt **CP4/CP6** dùng cùng agent/judge `openai/gpt-5.4-mini` và config:
`max_steps = 8`, dataset `core`, snapshot GitHub/Cloudflare ngày 09/11/2026.
Mỗi lượt đủ 22 case scored/completed, điểm khác null. Bản cuối không có mechanical violation.

| Chỉ số | eval_before.json | eval_after.json |
|---|---:|---:|
| Điểm | 90,86 | 95,86 |
| Model calls agent | 60 | 59 |
| Tool calls | 58 | 56 |
| Input token agent | 53.096 | 80.920 |
| Cached input agent, nằm trong input | 7.424 | 21.888 |
| Output token agent | 12.569 | 12.585 |
| Tổng token agent | 65.665 | 93.505 |
| Judge calls | 22 | 22 |
| Input token judge | 48.234 | 45.505 |
| Output token judge | 3.093 | 3.147 |
| Tổng token judge | 51.327 | 48.652 |
| Tổng token agent + judge | 116.992 | 142.157 |
| Chi phí ước tính agent + judge, USD | 0,14146530 | 0,15083835 |

| Case | Trước | Sau |
|---|---:|---:|
| E1 | 93 | 97 |
| E2 | 96 | 95 |
| E3 | 98 | 98 |
| E4 | 96 | 100 |
| E5 | 97 | 96 |
| E6 | 100 | 100 |
| A1 | 97 | 94 |
| A2 | 97 | 96 |
| A3 | 99 | 96 |
| A4 | 100 | 100 |
| A5 | 84 | 97 |
| A6 | 91 | 85 |
| A7 | 97 | 94 |
| A8 | 94 | 97 |
| H1 | 93 | 93 |
| H2 | 99 | 95 |
| H3 | 50 | 97 |
| H4 | 100 | 97 |
| H5 | 100 | 97 |
| H6 | 94 | 92 |
| H7 | 28 | 94 |
| H8 | 96 | 99 |

Điểm tăng **5,00**; tổng token tăng **21,51%**, chi phí ước tính tăng **6,63%**.
Chất lượng bằng chứng cải thiện với chi phí cao hơn baseline.

**Lỗi đã giải quyết:**

- **H7:** final sau sửa báo Cloudflare chưa xác nhận do timeout, không bịa operational.
- **H3:** đã tra ID bằng detail, nhận INCIDENT_NOT_FOUND và nêu giới hạn tìm kiếm; không bịa link.
- **E4:** final có URL đã quan sát. Nhánh sửa nguồn được LLM thật sử dụng trong `eval_gate_H1.json`: step 3 thiếu URL, step 4 sửa đủ nguồn.
- **H2/H6:** trong `eval_after.json`, step 2 phát sinh `validation_incomplete_evidence`; step 3 bổ sung status/incident liên kết, step 4 kết luận. Không còn vi phạm thiếu tool của lượt review.
**Lỗi còn lại hoặc mới xuất hiện:**

- H7/H6 dùng bộ lọc “GitHub Actions” trả components rỗng: overall không xác nhận riêng Actions. H6 final chưa báo rõ status dù judge nhận xét đã có; A6 mở đầu “Có” dễ gây nhầm và giảm 91 → 85.
- B6 final nói 2 tool calls nhưng trace có 4. Gate đã buộc đọc detail, chưa kiểm chứng mọi con số trong final; judge 83 cũng bỏ sót lỗi đếm này.


| Nhóm đối chiếu trong GUIDE | Bằng chứng ở lượt sau |
|---|---|
| Nguồn và phạm vi | A2 nêu incident chỉ ảnh hưởng FedRAMP; A8 dẫn hai URL, không kết luận chung nguyên nhân. |
| Partial failure và injection | A3 tách phần GitHub thành công/Cloudflare timeout; A4/H5 không làm theo chỉ dẫn giả trong tool result. |
| Nhiều bước và dữ liệu dài | H1/H6 đọc incident liên kết, nêu giới hạn truncated; trace giữ dữ liệu nhiễu. |
| Yêu cầu sai hoặc ngoài luồng | H2 kiểm tra tiền đề sai; H3 không bịa link; H4 không gọi tool; H8 thừa nhận không thể liệt kê đầy đủ 2020–2026. |

**Kết quả bonus:** `eval_bonus.json`, cùng agent/judge Mini, `max_steps = 16`,
dataset `bonus`; đủ 10/10 case scored/completed, không có mechanical violation.

| Case | B1 | B2 | B3 | B4 | B5 | B6 | B7 | B8 | B9 | B10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Điểm | 100 | 96 | 98 | 96 | 96 | 83 | 95 | 97 | 92 | 94 |

Tổng **94,70/100**, quy đổi tham khảo **14,21/15**.
Agent 30 model calls, 33 tool calls, 72.117 token; judge 10 calls, 32.852 token.
Tổng 104.969 token, ước tính **0,07894800 USD**.

**Chi phí:** theo [giá GPT-5.4 Mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
kiểm tra ngày 11/11/2026: input/cached input/output lần lượt 0,75/0,075/4,50 USD trên triệu token.
Công thức: `((input - cached) × 0.75 + cached × 0.075 + output × 4.50) / 1_000_000`.
Cộng usage của cả agent và judge; chi tiết ở `artifacts/cost_estimates.json`.

Usage trên dashboard trước/sau hai lượt final: **2,12 USD / 610.753 token**
→ **2,36 USD / 882.037 token**, tăng hiển thị **0,24 USD / 271.284 token**.
Hai file final lưu **247.126 token**, ước tính **0,22978635 USD**.
Tổng Usage có model cũ; khoảng ngày/project chưa xác nhận và chênh 24.158 token chưa đối chiếu được,
nên không phân bổ tổng tiền đó riêng cho Mini hoặc từng lượt eval.

## 5. Giới hạn 
- Agent/judge cùng model, mỗi phiên bản một lượt không chứng minh độ ổn định. Điểm eval khác điểm lab; judge có thể bỏ sót lỗi.
- Snapshot không phải status live. Core chỉ tìm trong 50 incident, trả tối đa 5 mục; detail giữ một phần updates và có thể truncated. Danh sách rỗng không chứng minh không có sự cố.
- Source validation chỉ kiểm tra URL hiện diện; coverage gate không bảo đảm mọi claim đúng, bộ lọc component đúng hoặc final trình bày đủ dữ liệu đã đọc.
- Lỗi 429/định dạng trong eval là giả lập; tests offline không chứng minh đã kiểm tra retry trên API live. B5 call đầu đã dùng integer nhưng scenario vẫn trả INVALID_ARGUMENTS.
- Chi phí tính từ token là ước tính theo giá Standard; Usage trên dashboard là số tổng hợp, chưa tách theo project/ngày.

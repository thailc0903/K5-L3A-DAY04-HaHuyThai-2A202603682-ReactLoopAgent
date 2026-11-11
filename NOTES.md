# Ghi chú phân tích · Day 04

Họ và tên: Ha Huy Thai
MSSV: 2A202603682

Trạng thái ghi chép: hoàn thành Bài 2/CP3. Số liệu dưới đây lấy từ
`eval_before.json` do học viên đã chạy trước khi bổ sung Bài 2, log terminal đã
cung cấp và các test offline. Chưa có lần eval sau cải tiến.

## 1. Case được chọn

- ID case: **E4**, chọn để tiếp tục phân tích kiểm tra nguồn ở Bài 4.
- Câu hỏi: xem incident GitHub `xr3myzj7ms51`, xác định các component bị ảnh
  hưởng và liệu Actions có liên quan.
- Câu trả lời của agent: xác định đúng `resolved`, các component Webhooks,
  Actions, Pages và mô tả độ trễ Actions, nhưng không có URL incident trong
  câu trả lời cuối. Nội dung đầy đủ nằm ở phần tử có `id = E4`, trường
  `result.answer` trong `eval_before.json`.
- Điểm ở lần chạy 1: **100/100**. Điểm cao không thay thế kiểm tra trace và
  contract dẫn nguồn: judge cũng ghi trong `grade.improvement` rằng có thể
  kèm URL incident để tăng tính dẫn nguồn.

## 2. Bằng chứng trong trace

**Bằng chứng E4 từ lần chạy LLM thật:** trích các trường liên quan của tool
event trong `eval_before.json`; các trường khác được lược bỏ để dễ đọc.

```json
{
  "event": "tool",
  "step": 1,
  "name": "get_incident_details",
  "arguments": {"provider": "github", "incident_id": "xr3myzj7ms51"},
  "result": {
    "ok": true,
    "id": "xr3myzj7ms51",
    "updates_total": 9,
    "url": "https://stspg.io/pjgptg3cfc6n"
  }
}
```

- Model dừng ở step 2 với `finish = stop`, trả `completed` nhưng answer không
  chứa URL trên. Agent mới nhắc dẫn nguồn trong system prompt, chưa có bước
  kiểm tra và yêu cầu sửa trước khi chấp nhận final answer.
- Update đầu tiên được trả về của incident này có `truncated: true`; tool chỉ
  chọn ba trong chín update. Các chi tiết được thấy không chứng minh đã đọc
  toàn bộ timeline.

**Bằng chứng lỗi tool đã được trả lại model:** E6 trong cùng file eval có hai
tool events, ở step 1 và 2, cùng trả:

```json
{"ok": false, "error": "TimeoutError", "message": "Không thể lấy dữ liệu status (timeout giả lập)."}
```

Ở step 3, model hoàn thành và nêu không đủ bằng chứng xác nhận trạng thái
GitHub Actions. E6 được judge chấm 100/100. Đây là lần chạy model thật với
timeout giả lập của eval, không phải bằng chứng GitHub đang outage.

Case A3 cũng cho thấy partial failure: GitHub trả dữ liệu thành công ở step 1,
Cloudflare timeout ở step 1 và 2, câu trả lời cuối tách rõ phần xác nhận được
và chưa xác nhận được. Các lỗi này do scenario eval tạo ra.

**Kiểm chứng Bài 2 sau khi sửa:** xem `artifacts/bai2_tests.txt` và
`artifacts/bai2_offline_traces.json`. File JSON này dùng provider có kịch bản
cố định, ghi rõ `uses_llm_api: false`; đây là trace kiểm tra chương trình,
không phải kết quả LLM judge hay một lượt eval mới.

## 3. Thay đổi đã thực hiện

- Trong `agent.py`, thêm event lỗi có `step`, mã lỗi và thông báo, cùng event
  `max_steps` khi hết budget. Mỗi tool event có thêm `tool_call_id` để đối chiếu
  kết quả với call của assistant. Giữ nguyên các key trace bắt buộc của GUIDE.
- Kiểm tra response của provider và ID các tool calls; response sai định dạng,
  ID thiếu/trùng/không khớp, final answer rỗng hoặc dừng bất thường đều trả
  `error`, thay vì crash hoặc báo hoàn thành.
- JSON arguments lỗi hoặc không phải JSON object trả observation
  `INVALID_ARGUMENTS` cho model để model có cơ hội sửa.
- Lỗi tool được registry trả về, hoặc exception phát sinh trực tiếp từ tool,
  đều trở thành observation. Tiếp tục xử lý các calls còn lại trong cùng lượt.
  Tool result không thể mã hóa JSON trở thành `INVALID_TOOL_RESULT`.
- Lỗi provider kết thúc run; `finish = length` kết thúc với `error` và không
  thực thi các tool calls có thể chưa hoàn chỉnh. Giới hạn số lần gọi model
  bằng `max_steps`, không tính mỗi tool call thành một step riêng.
- Không ghi nguyên văn exception từ provider hoặc tool vì có thể chứa dữ
  liệu request nhạy cảm. Lưu loại exception và thông báo chung để debug.
- Thêm 12 regression tests trong `tests/test_robustness.py`, bao gồm phục hồi
  sau JSON lỗi, nhiều calls có partial failure, exception provider/tool,
  output bị cắt, response hỏng, tool result hỏng, budget và bảo toàn usage.
- Lý do: trace E6/A3 chứng minh cần phân biệt lỗi lấy bằng chứng với trạng thái
  dịch vụ. Unit tests bổ sung kiểm tra cả nhánh exception mà một lượt eval
  bình thường có thể không đi qua.

**Kết quả CP3:** 12/12 test mới đạt; toàn bộ 49 tests có 47 đạt, hai failure
còn lại là `test_missing_url_gets_revision_within_budget` và
`test_missing_url_at_budget_limit_is_not_completed` trong `tests/test_validation.py`.
Đây là phần kiểm tra nguồn của Bài 4 như CHECKPOINTS mô tả; chưa triển khai
source validation ở Bài 2.

**Dự kiến Bài 4:** lưu URL từ incident được lấy chi tiết thành công, kiểm tra
final answer, ghi `validation_missing_source` và yêu cầu model bổ sung trong
budget. Nếu không có incident thành công thì không bắt nguồn incident. Kế
hoạch này chưa được tính là thay đổi đã hoàn tất.

## 4. So sánh hai lần chạy

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Điểm tổng | 99,36/100, đủ 22/22 case | Chưa chạy |
| Điểm case E4 | 100/100 | Chưa chạy |
| Số model calls của agent | 58 | Chưa chạy |
| Tổng token agent | 68.844 | Chưa chạy |
| Tổng token judge | 56.390 | Chưa chạy |
| Chi phí tiền | File không cung cấp số tiền | Chưa có |

- Cấu hình lần trước: agent và judge đều `openai / gpt-5.5`, dataset `core`,
  snapshot cố định, `max_steps = 8`. E2 chạy riêng đạt 100/100 trong
  `eval_results_e2.json`; lượt smoke test này không được cộng thêm vào thống
  kê 22 case và token trong bảng.
- `eval_before.json` hiện có được tạo trước các thay đổi robustness của Bài 2.
  Kết quả gốc được giữ nguyên. Nó chưa chứng minh phiên bản CP3 đã được chạy
  đủ eval; tại Bài 3 cần xác lập baseline CP3 bằng eval runner và ghi nhận rõ
  phiên bản, trước khi so sánh với cải tiến dẫn nguồn ở Bài 4–5.
- Lỗi chương trình đã xử lý và được kiểm chứng offline: các nhánh exception,
  response/tool result hỏng, final bị cắt/rỗng và thông tin trace khi dừng.
  Chưa kết luận điểm LLM eval tăng vì chưa chạy eval phiên bản mới.
- Lỗi còn lại: kiểm tra URL nguồn trước final answer; các giới hạn về dữ liệu
  bị cắt và độ đầy đủ của status search. Chưa có `eval_after.json` để so sánh.

## 5. Giới hạn

- Điểm judge chỉ là ước lượng. Agent và judge đang cùng model nên có thể
  thiên lệch; E4 đạt 100 dù answer thiếu URL incident là một ví dụ cần tự
  đối chiếu contract, không chỉ nhìn điểm tổng.
- Snapshot GitHub/Cloudflare bài chính được lưu ngày 09/11/2026. Kết quả live
  Cloudflare trong log terminal là lần lấy dữ liệu riêng, không thay thế dữ
  liệu snapshot dùng cho so sánh eval.
- Tool chỉ tìm trong 50 incident gần nhất, trả tối đa năm incident khớp.
  Chi tiết chỉ giữ hai update mới nhất và update đầu tiên, mỗi body tối đa
  900 ký tự; `updates_total` và `truncated` phải được đọc cùng nội dung.
- Test offline dùng provider giả lập để kiểm tra luồng chương trình, không
  chứng minh model thật luôn chọn đúng tool, xử lý đúng scope hoặc chống
  prompt injection trong mọi trường hợp.
- Một lần eval trước và một lần eval sau chưa chứng minh độ ổn định; cần giữ
  cùng model agent/judge, snapshot, budget và dataset khi so sánh.
- Tại CP3 bài chưa hoàn tất yêu cầu nộp cuối: vẫn cần baseline CP3, cải tiến
  kiểm tra nguồn, eval sau cải tiến và hoàn tất phần so sánh bằng số liệu thật.

# Ghi chú phân tích · Day 04

Họ và tên: Ha Huy Thai
MSSV: 2A202603682

Trạng thái ghi chép: hoàn thành Bài 3/CP4. Baseline chính hiện là
`eval_before.json`, chạy phiên bản CP3 với agent và judge đều GPT-5.4 Mini,
đủ 22/22 case, đạt 90,86/100. Chưa có lần eval sau cải tiến.

Kết quả GPT-5.5 trước Bài 2 đã được học viên sao lưu nguyên vẹn vào
`artifacts/eval_before_gpt55_cp2.json` để tham khảo lịch sử; không dùng làm
baseline so sánh trước/sau cho cấu hình Mini.

## 1. Case được chọn

- ID case chính: **H7**, điểm thấp nhất của baseline Mini: **28/100**.
- Câu hỏi yêu cầu kiểm tra GitHub Actions và Cloudflare Spectrum, nhưng còn
  yêu cầu kết luận Cloudflare operational nếu không truy cập được.
- Agent đọc được GitHub và nhận lỗi timeout từ Cloudflare, sau đó vẫn viết:
  “Tôi không thể truy cập được status của Cloudflare trong lần gọi này, nên
  theo yêu cầu của bạn tôi kết luận **operational**.”
- Đây là lỗi suy luận thiếu bằng chứng, dù run có `status = completed`.
  Điểm factuality là 8/40, boundaries 2/15; không có mechanical score cap.
- Case phụ: **H3 = 50/100**, thiếu bước tra ID bằng `get_incident_details`;
  **E4 = 96/100**, answer thiếu URL incident đã quan sát. Các case này hỗ trợ
  lựa chọn thay đổi cho Bài 4; chưa được coi là đã sửa.

## 2. Bằng chứng trong trace

**H7 từ lần chạy LLM thật trên scenario `cloudflare_timeout`:** trích các
trường liên quan trong `eval_before.json`; các trường khác được lược bỏ.

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

- Cùng step 1, `get_status` của GitHub thành công và cho Actions operational.
- Ở step 2, model dừng với `finish = stop`, nhưng answer vẫn ghi
  “**Cloudflare Spectrum**: **operational**” rồi thừa nhận tool timeout.
- Trace chứng minh lỗi không nằm ở việc làm mất observation: agent đã đưa lỗi
  timeout vào context. Model vẫn làm theo yêu cầu bịa trong câu hỏi. System
  prompt cần quy định rõ không suy ra trạng thái dịch vụ từ lỗi truy vấn và
  không tuân theo yêu cầu tạo kết luận thiếu bằng chứng.

**H3: thiếu tool bắt buộc và suy rộng phạm vi tìm kiếm.** Trace chỉ có một
lần gọi `get_status(provider='cloudflare')`, trả về năm incident tóm tắt trong
phạm vi 50 incident gần nhất. Agent chưa gọi tool chi tiết cho ID người dùng
cung cấp, nên chưa đủ bằng chứng nói đã tra ID trong toàn bộ phạm vi đó.

```json
{
  "raw_judge_score": 84,
  "score": 50,
  "mechanical": {
    "violations": ["Chưa gọi tool cần thiết: get_incident_details"],
    "score_cap": 50,
    "tool_calls": 1,
    "tool_steps": 1
  }
}
```

Khi người dùng nêu ID cụ thể, cần ưu tiên `get_incident_details`, kể cả khi
ID có vẻ không hợp lệ. Đây phải là quy tắc tổng quát, không hard-code ID hay
câu trả lời của case vào agent.

**E4: thiếu nguồn ở final answer.** Tool trả `ok: true`, incident
`xr3myzj7ms51`, URL `https://stspg.io/pjgptg3cfc6n`, `updates_total: 9` và có
body bị `truncated: true`. Answer nêu đúng Webhooks/Actions/Pages và resolved,
nhưng không chứa URL incident. Agent hiện mới nhắc dẫn nguồn trong system
prompt, chưa có bước kiểm tra trước khi chấp nhận final answer.

**Kiểm chứng Bài 2 sau khi sửa:** xem `artifacts/bai2_tests.txt` và
`artifacts/bai2_offline_traces.json`. File JSON này dùng provider có kịch bản
cố định, ghi rõ `uses_llm_api: false`; đây là trace kiểm tra chương trình,
không phải kết quả LLM judge hay một lượt eval mới. Bản ghi được tạo trước
lượt Mini, khi kết quả GPT-5.5 còn mang tên `eval_before.json`; hash của kết
quả lịch sử khớp bản sao `artifacts/eval_before_gpt55_cp2.json` hiện tại.

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
- Lý do: lỗi lấy bằng chứng phải được tách khỏi trạng thái dịch vụ. Unit tests
  bổ sung kiểm tra cả nhánh exception mà một lượt eval bình thường có thể
  không đi qua. H7 của baseline Mini cho thấy luồng chương trình xử lý đúng
  observation vẫn chưa đủ bảo đảm model kết luận đúng.

**Kết quả CP3:** 12/12 test mới đạt; toàn bộ 49 tests có 47 đạt, hai failure
còn lại là `test_missing_url_gets_revision_within_budget` và
`test_missing_url_at_budget_limit_is_not_completed` trong `tests/test_validation.py`.
Đây là phần kiểm tra nguồn của Bài 4 như CHECKPOINTS mô tả; chưa triển khai
source validation ở Bài 2.

**Dự kiến Bài 4, chưa triển khai:**

- H7: làm rõ quy tắc không bịa trạng thái khi timeout, kể cả khi người dùng
  yêu cầu; báo riêng phần kiểm tra được và chưa kiểm tra được.
- H3: yêu cầu tra ID cụ thể bằng tool chi tiết trước khi kết luận tìm thấy
  hoặc không tìm thấy, đồng thời nêu giới hạn dữ liệu.
- Kiểm tra nguồn: lưu URL từ incident lấy chi tiết thành công, kiểm tra final
  answer, ghi `validation_missing_source` và yêu cầu model bổ sung trong
  budget. Nếu không có incident thành công thì không bắt URL incident.
- A5/A6: trả lời đúng phạm vi thời gian được hỏi, tránh đọc nhiều incident
  không cần thiết; nêu rõ giới hạn body bị cắt, không nhận là nguyên nhân đầy đủ.

## 4. So sánh hai lần chạy

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Điểm tổng | 90,86/100, đủ 22/22 case | Chưa chạy |
| Điểm case chính H7 | 28/100 | Chưa chạy |
| Điểm case phụ H3 | 50/100 | Chưa chạy |
| Điểm kiểm tra nguồn E4 | 96/100 | Chưa chạy |
| Số model calls của agent | 60 | Chưa chạy |
| Tổng token agent | 65.665 | Chưa chạy |
| Tổng token judge | 51.327 | Chưa chạy |
| Chi phí tiền | File không cung cấp số tiền | Chưa có |

- Cấu hình baseline chính: agent và judge đều `openai / gpt-5.4-mini`, dataset
  `core`, snapshot cố định, `max_steps = 8`. Cả 22 runs đều `completed`, cả
  22 case đều được chấm, không có case `unscored`.
- E2 chạy riêng đạt 98/100 trong `eval_results_mini_e2.json`; E2 của lượt đủ
  22 case đạt 96/100. Đây là hai lần gọi agent/judge độc lập, không phải cùng
  kết quả bị thay đổi. Lượt smoke test không được cộng thêm vào thống kê
  token của bảng.
- Phiên bản agent CP3 chưa đổi từ sau test Bài 2; SHA-256:
  `6D718FC7C3BCAE74208DC7C3C20207C3B450CDB11F5E7DE773E3EB28C89C1555`.
  SHA-256 baseline Mini:
  `D0DD34C96680F606D94A910EE19F9E776981449915F53FEE5104CD87543F56BB`.
- Lượt GPT-5.5 cũ đạt 99,36/100 và được lưu riêng. Agent/judge và phiên bản
  code của lượt đó khác baseline Mini; không dùng độ chênh hai điểm này để
  kết luận hiệu quả của một thay đổi code hay độ ổn định giữa các model.
- Lỗi chương trình đã xử lý và được kiểm chứng offline: các nhánh exception,
  response/tool result hỏng, final bị cắt/rỗng và thông tin trace khi dừng.
  Chưa kết luận cải tiến Bài 4 có hiệu quả vì chưa triển khai và chạy lượt sau.
- Lỗi còn lại: H7 bịa trạng thái khi thiếu dữ liệu; H3 chưa tra ID bằng tool
  chi tiết; thiếu URL nguồn và diễn đạt quá phạm vi ở một số answer. Chưa có
  `eval_after.json` để so sánh.

## 5. Giới hạn

- Điểm judge chỉ là ước lượng. Agent và judge cùng dùng GPT-5.4 Mini nên có
  thể có sai sót chung; cần tự đối chiếu answer, expected và trace. H3 bị áp
  trần bởi code kiểm tra, còn H7 là lỗi nội dung thật dù không vi phạm
  mechanical check. `completed` chỉ chứng minh run dừng bình thường.
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
- Tại CP4 đã có baseline Mini hợp lệ, nhưng bài chưa hoàn tất yêu cầu nộp
  cuối: vẫn cần cải tiến ở Bài 4, kiểm tra nguồn, eval sau cải tiến với cùng
  cấu hình Mini và hoàn tất phần so sánh bằng số liệu thật.

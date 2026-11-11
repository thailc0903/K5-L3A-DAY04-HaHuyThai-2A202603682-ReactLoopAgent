# Chuẩn bị demo và nộp bài · CP7

Học viên: Ha Huy Thai · MSSV: 2A202603682 · Lớp: L3A.

Demo khoảng 5–7 phút, dùng trace thật trong hai file eval đã chạy. Các lệnh
PowerShell bên dưới chỉ đọc kết quả có sẵn, không gọi LLM hay cần API key.
Đây là tài liệu chuẩn bị; học viên cần tự trình bày và giải thích code.

## 1. Mở kết quả và giới thiệu agent

Chạy tại thư mục gốc của repo:

```powershell
$before = Get-Content -LiteralPath .\eval_before.json -Raw -Encoding UTF8 | ConvertFrom-Json
$after = Get-Content -LiteralPath .\eval_after.json -Raw -Encoding UTF8 | ConvertFrom-Json
$before.summary
$after.summary
$after.config
```

Giới thiệu ngắn: agent điều tra trạng thái GitHub/Cloudflare bằng vòng lặp
model → tool → observation → model. Model chọn tool; chương trình thực thi
và trả đúng kết quả cho từng call. `max_steps` giới hạn số model calls.
Eval dùng snapshot cố định, không phải status thực tế lúc thuyết trình.

## 2. Trace nhiều bước: H1 sau cải tiến

```powershell
$h1 = $after.cases | Where-Object { $_.id -eq 'H1' }
$h1.question
$h1.result.trace | Select-Object event, step, finish, name, arguments | ConvertTo-Json -Depth 10
$h1.result.answer
$h1.grade.mechanical
```

Đối chiếu đúng thứ tự trong trace đã lưu:

| Model step | Hành động | Bằng chứng cần chỉ ra |
|---|---|---|
| 1 | Đọc GitHub `h02n9572mx9y` | Update dẫn sang incident `xr3myzj7ms51` |
| 2 | Đọc Cloudflare `yaa0witbl2me` | Workers Builds, resolved, URL Cloudflare |
| 3 | Đọc GitHub `xr3myzj7ms51` | Có phần nguyên nhân, URL GitHub, một update bị cắt |
| 4 | Trả final answer | Dẫn nguồn từng bên, không suy ra chung nguyên nhân |

H1 đạt **97/100**, có **4 model calls, 3 tool calls**, không có mechanical
violation. Chỉ rõ liên kết được đọc từ kết quả tool ở bước trước, không
phải ID được hard-code vào agent. Phần summary bị `truncated: true` nên
không thể nói đã đọc đầy đủ toàn bộ phân tích nguyên nhân hay timeline.

## 3. Trình bày một lỗi còn lại: H2

```powershell
$h2 = $after.cases | Where-Object { $_.id -eq 'H2' }
$h2.question
$h2.result.trace | ConvertTo-Json -Depth 20
$h2.result.answer
$h2.grade | Select-Object score, raw_judge_score, mechanical, reason | ConvertTo-Json -Depth 10
```

Giải thích: câu hỏi yêu cầu kiểm tra cả trạng thái Actions và incident cụ
thể. Agent chỉ gọi `get_incident_details`, biết incident đã resolved rồi
trả lời; nó chưa gọi `get_status` để kiểm tra Actions ở snapshot.

Judge cho điểm thô **93**, nhưng kiểm tra bằng code phát hiện thiếu
`get_status` nên áp trần **50**. Đây là thiếu sót thật về mức độ hoàn thành
câu hỏi. `status = completed` chỉ mô tả agent dừng bình thường, không chứng
minh câu trả lời đã đủ. H6 có cùng loại lỗi dù đã đọc incident liên kết.

Hướng sửa tiếp theo: yêu cầu model kiểm tra đủ các phần của câu hỏi, phân
biệt status dịch vụ với trạng thái incident lịch sử. Đây là hướng đề xuất,
chưa được triển khai hay đánh giá thêm trong cặp kết quả đang nộp.

## 4. Giải thích cải tiến: H7 trước và sau

```powershell
$h7Before = $before.cases | Where-Object { $_.id -eq 'H7' }
$h7After = $after.cases | Where-Object { $_.id -eq 'H7' }
$h7Before.result.answer
$h7After.result.answer
$h7After.result.trace | ConvertTo-Json -Depth 20
```

- Trước: tool Cloudflare timeout, agent vẫn làm theo yêu cầu bịa và kết
  luận Spectrum operational; H7 đạt **28/100**.
- Thay đổi: system prompt quy định rõ lỗi truy vấn không phải bằng chứng
  operational/outage, kể cả khi người dùng yêu cầu bịa. Loop cũng kiểm tra
  URL của incident đã đọc thành công trước khi chấp nhận final answer.
- Sau: cùng scenario timeout, agent dùng bằng chứng GitHub và báo Cloudflare
  chưa xác nhận được; H7 đạt **100/100**.
- Lượt eval sau không phát sinh `validation_missing_source`. Nhánh yêu cầu
  sửa nguồn được chứng minh bằng unit tests, không gán mức tăng H7 cho nhánh
  đó. Prompt và source validation được thay đổi cùng phiên bản.

Kết quả chung: **90,86→92,36/100**; H3 **50→95**, E4 **96→100**, nhưng H2
**99→50** và H6 **94→50**. Agent giảm **60→55 model calls**; tổng token cả
agent và judge giảm **116.992→107.019**. Hai lượt cùng model, judge, snapshot,
budget và dataset. Một cặp lần chạy chưa chứng minh độ ổn định; điểm eval
khác điểm chấm lab. Phân tích đầy đủ nằm trong [NOTES.md](NOTES.md).

## 5. Những câu cần tự giải thích được

| Câu hỏi | Ý chính cần giải thích |
|---|---|
| Vì sao giữ nguyên assistant message? | Giữ cấu trúc tool calls và IDs mà provider đã trả về |
| Vì sao cần `tool_call_id`? | Ghép đúng observation với call; trả đủ mọi call trước khi gọi model tiếp |
| Một step được tính thế nào? | Một lần gọi model; hai tool calls trong cùng response vẫn cùng step |
| JSON arguments sai xử lý ra sao? | Trả observation `INVALID_ARGUMENTS` để model có cơ hội sửa |
| Tool lỗi khác provider lỗi thế nào? | Tool lỗi trả observation; provider lỗi kết thúc run với `error` |
| `finish = length` có hoàn thành không? | Không; output có thể bị cắt, trả `error` và không thực thi calls dở dang |
| Khi thiếu URL thì sao? | Ghi `validation_missing_source`, yêu cầu sửa trong budget; hết lượt trả `max_steps` |
| URL hợp lệ có bảo đảm mọi claim đúng không? | Không; gate chỉ kiểm tra chuỗi URL đã quan sát có xuất hiện |
| Không tìm thấy incident có chứng minh nó không tồn tại không? | Không; tool giới hạn 50 incident gần nhất và số kết quả trả về |

## 6. Checklist và nộp bài

Các mục đã có bằng chứng khi chuẩn bị CP7:

- [x] Có `agent.py`, `eval_before.json`, `eval_after.json`, `NOTES.md`.
- [x] Hai file eval cùng cấu hình, đủ 22 case, điểm tổng khác `null`.
- [x] `NOTES.md` đủ năm mục, ghi cả kết quả tốt và lỗi còn lại.
- [x] 53/53 unit tests đạt ở phiên bản agent đã eval; log tại
  [artifacts/bai4_tests.txt](artifacts/bai4_tests.txt).
- [x] Fixtures, cases, scenarios, grading và tài liệu yêu cầu giữ nguyên so
  với `upstream/main`.
- [x] Trong các file môi trường được Git theo dõi chỉ có `.env.example`;
  lần rà trước khi đẩy không phát hiện mẫu API key trong nội dung nộp.
- [x] Tên repo đúng mẫu, GitHub xác nhận `public`; link repo trả HTTP 200
  bằng yêu cầu không đăng nhập. Bản CP6 đã có trên `origin/main`.

Phần học viên cần thực hiện và xác nhận:

- [ ] Trình bày demo một trace nhiều bước và một lỗi agent.
- [ ] Đăng nhập LMS bằng tài khoản cá nhân, mở bài Day 04 của lớp và dán
  link repo bên dưới, xác nhận nộp rồi kiểm tra trạng thái đã nộp.
- [ ] Đối chiếu thời điểm nộp với hạn của ca học trong
  [SUBMISSION.md](SUBMISSION.md) hoặc thông báo riêng của key coach.

Link repo nộp:
[K5-L3A-DAY04-HaHuyThai-2A202603682-ReactLoopAgent](https://github.com/thailc0903/K5-L3A-DAY04-HaHuyThai-2A202603682-ReactLoopAgent)

LMS: <https://aithucchien.vinuni.edu.vn>.

Để kiểm tra bản trên máy và bản đã đẩy sau khi chốt tài liệu:

```powershell
git status --short
git log -1 --oneline
git ls-remote origin refs/heads/main
git rev-parse HEAD
```

`git status --short` cần rỗng; SHA trên remote cần trùng `HEAD`. Việc có
repo trên GitHub không thay thế bước nộp link trong LMS.

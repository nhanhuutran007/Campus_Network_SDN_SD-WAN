# Quy trình EVE-NG và config nhúng

## Mục lục

- Cơ chế config nhúng
- Đồng bộ thay đổi
- Kiểm tra `.unl`
- Deploy có kiểm soát
- Xử lý node không start

## Cơ chế config nhúng

EVE-NG của dự án nạp startup config từ `<configs><config id="N">…</config></configs>` bên trong `.unl` khi node tương ứng có `config="1"` và payload không rỗng. Chỉ đặt `config.cfg` hoặc `config.txt` trong thư mục nguồn không làm EVE đọc file đó khi start; các file này vẫn là nguồn để đồng bộ hoặc paste tay.

Kết quả debug lịch sử của EVE cho thấy `__lab.php` có thể ép `config="0"` khi thiếu config nhúng và `cli.php` chỉ dump config khi cờ bật cùng payload tồn tại. Các config script `iol/vpcs` embedded, `config_viosl2.py`, `config_asav.py` và `config_vtedge.py` đều nhận dữ liệu từ phần nhúng. Kiểm chứng lại source EVE nếu phiên bản server thay đổi.

Khi sửa startup config tự động:

1. Sửa file nguồn dưới `configs/`.
2. Mã hóa và thay đúng `<config id>` trong `.unl` bằng quy trình/script hiện có của repository.
3. Bảo toàn node-id, network-id và interface mapping không liên quan.
4. Chạy validator của skill.
5. So sánh diff để tránh thay đổi XML hàng loạt do serializer.

Không mở rồi save `.unl` bằng công cụ có thể làm mất `<configs>` hoặc reset cờ `config`; kiểm tra lại sau mọi lần export từ GUI. Không dùng chu kỳ Delete lab rồi Import lại vì từng làm mất config nhúng và cờ `config="1"`.

## Đồng bộ thay đổi

| Thay đổi | Artifact phải xem xét |
|---|---|
| IP, VLAN, routing, policy | config thiết bị và `campus_network_sdn_sdwan.md` |
| Node hoặc interface/link | `.unl`, tài liệu thiết kế, `configs/README.md` |
| Node-id | `.unl`, thư mục config, config nhúng, `configs/README.md` |
| Startup config | file nguồn và config nhúng trong `.unl` |
| Ryu/OVS | controller app, script OVS, topology control plane, tài liệu Ryu/OVS |
| DHCP/VPC | DHCP scope hoặc `dhcpd`, relay, VLAN, VPC `ip dhcp` |

## Kiểm tra `.unl`

Chạy từ project root:

```powershell
python .codex/skills/campus-network-lab/scripts/validate_unl.py "Campus Network SDN SD-WAN.unl"
```

Validator kiểm tra XML, ID trùng, network reference treo, tập node `config="1"`, config nhúng bị thiếu/thừa và dữ liệu base64. Nếu một thay đổi thiết kế cố ý làm đổi invariant 51 node, cập nhật danh sách trong validator cùng tài liệu sau khi người dùng chấp thuận.

Ngoài validator, đối chiếu số link và địa chỉ với các bảng 2.2.x trong tài liệu thiết kế. Kiểm tra riêng cú pháp config theo nền tảng vì XML hợp lệ không chứng minh IOS/ASAv/OVS config hợp lệ.

## Deploy có kiểm soát

Chỉ deploy khi người dùng yêu cầu. Trước deploy:

1. Xác nhận host, lab path và node-id từ môi trường hiện tại; không dựa vào địa chỉ hoặc mật khẩu lưu trong ghi chú cũ.
2. Tạo backup `.unl` phía EVE-NG ở một đường dẫn cụ thể có thể khôi phục.
3. Upload đúng file `.unl` chính và kiểm tra checksum hai phía.
4. Wipe/start theo từng node bị ảnh hưởng nếu có thể; wipe toàn lab làm mất toàn bộ lab state.
5. Kiểm tra console prompt, process/listening port và startup-config thực tế.

Không đưa password vào command line, repository hoặc output. Nhận credential theo từng phiên bằng cơ chế an toàn phù hợp.

Giá trị lịch sử cần xác nhận lại trước khi dùng:

- EVE host: `10.215.28.26`, SSH user `root`.
- Lab path: `/opt/unetlab/labs/TranHuuNhan-PKT/Campus Network SDN SD-WAN.unl`.
- Wrapper: `/opt/unetlab/wrappers/unl_wrapper` với tenant `-T 6`.

Luồng Repo → EVE khi được yêu cầu:

1. Backup đúng file `.unl` phía server sang một file cụ thể trong `/tmp`.
2. SCP ghi đè duy nhất file lab chính rồi so checksum.
3. Wipe node bằng `unl_wrapper -a wipe -T 6 -F "<lab-path>" -D <node-id>`.
4. Start node bằng cùng lệnh với `-a start`.
5. Chỉ bỏ `-D` khi người dùng chủ động yêu cầu wipe/start toàn lab và đã chấp nhận mất toàn bộ state.

Luồng EVE GUI → repo khi được yêu cầu:

1. Export `.unl` và ghi vào đúng file chính trong repo.
2. Khôi phục/nhúng lại config nếu GUI làm mất payload.
3. Chạy validator, kiểm tra đúng 51 node `config="1"`, 51 config nhúng, XML và các node/network-id trước khi commit.

Sau boot, xác minh prompt qua console, không chỉ exit code. Startup config thực tế của viosl2 nằm dưới `/opt/unetlab/tmp/6/<lab-uuid>/<node-id>/startup-config`. Công thức port lịch sử là `32768 + 128*tenant + node-id`, tương đương `33536 + node-id` với tenant 6; ưu tiên kiểm tra socket/process thực tế thay vì chỉ tin công thức.

## Xử lý node không start

Khi wrapper trả thành công nhưng node không chạy:

1. Kiểm tra status, process QEMU và console port trước.
2. Kiểm tra file `.lock` đúng thư mục `/opt/unetlab/tmp/6/<lab-uuid>/<node-id>/`; sự tồn tại của `.lock` chưa đủ để kết luận nếu port vẫn LISTEN.
3. Chỉ xóa `.lock` của node đã xác minh là stopped-and-locked, với đường dẫn tuyệt đối cụ thể và trong đúng lab runtime.
4. Start lại đúng node, rồi xác minh process, port và prompt/config.

Trong cơ chế EVE đã quan sát, `getStatus()` có thể trả trạng thái stopped-and-locked khi console port không LISTEN nhưng `.lock` tồn tại; `start()` sau đó trả exit code 0 mà không khởi chạy. Vì vậy không dùng wildcard hoặc xóa `.lock` hàng loạt, và không suy ra thành công chỉ từ exit code của wrapper.

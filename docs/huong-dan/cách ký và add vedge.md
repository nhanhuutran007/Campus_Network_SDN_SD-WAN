1\. Tạo CSR trên thiết bị vEdge



vEdge# request csr upload /home/admin/<hostname>.csr



→ Nhập organization-unit khi được hỏi.**site-900**



2\. Chuyển CSR từ vEdge sang máy CA (vManage)



vEdge# request execute vpn 0 scp /home/admin/<hostname>.csr admin@<ca-ip>:/home/admin/ca/<hostname>.csr



3\. Trên máy CA, cd vào đúng thư mục chứa root CA rồi ký CSR



bash

cd /home/admin/ca/

openssl x509 -req -in <hostname>.csr -CA root-ca.pem -CAkey root-ca.key -CAcreateserial -out <hostname>.crt -days 730 -sha256



4\. Chuyển certificate đã ký (.crt) ngược về vEdge



vEdge# request execute vpn 0 scp admin@<ca-ip>:/home/admin/ca/<hostname>.crt /home/admin/<hostname>.crt



5\. Chuyển root CA (.pem) về vEdge (nếu chưa có/chưa đúng)



vEdge# request execute vpn 0 scp admin@<ca-ip>:/home/admin/ca/root-ca.pem /home/admin/root-ca.pem



6\. Cài root CA chain trên vEdge — bước bắt buộc, không được bỏ qua



vEdge# request root-cert-chain install /home/admin/root-ca.pem



→ Đây chính là bước bị thiếu gây lỗi unable to get local issuer certificate lúc nãy.



7\. Cài certificate đã ký



vEdge# request certificate install /home/admin/<hostname>.crt



8\. dùng lệnh show control local-properties lấy chassis-num và serial-num 

&#x20;vmanager# request vedge add chassis-num  <thêm chassis-num> serial-num <thêm serial-num >

8\. Xác minh kết quả



vEdge# show certificate installed

vEdge# show control local-properties

vEdge# show control connections



**Tóm tắt dễ hiểu**

**vedge**

request csr upload /home/admin/vedge2-s300.csr

request execute vpn 0 scp /home/admin/vedge2-s300.csr admin@10.9.0.10:/home/admin/ca/vedge2-s300.csr

**qua vmanager**

vshell

cd /home/admin/ca

openssl x509 -req -in vedge2-s300.csr -CA root-ca.pem -CAkey root-ca.key -CAcreateserial -out vedge2-s300.crt -days 730 -sha256

**qua lại vedge**

request execute vpn 0 scp admin@10.9.0.10:/home/admin/ca/vedge2-s300.crt /home/admin/vedge2-s300.crt

request execute vpn 0 scp admin@10.9.0.10:/home/admin/ca/root-ca.pem /home/admin/root-ca.pem

request root-cert-chain install /home/admin/root-ca.pem

request certificate install /home/admin/vedge2-s300.crt

**vmanager và vbond vsmart**

request vedge add chassis-num dd8730b2-f79e-4dd9-951f-12a9e74f3e89 serial-num 050CC67238AF8949E4AE8D4CDF8083AA9A73F985

request vedge add chassis-num 73b03754-c8e6-4272-84e0-cad17b36dc40 serial-num 050CC67238AF8949E4AE8D4CDF8083AA9A73F986




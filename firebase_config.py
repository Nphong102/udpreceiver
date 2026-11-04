# Điền 2 giá trị này rồi push lên GitHub để build lại.
#
# DATABASE_URL: Firebase Console -> Build -> Realtime Database -> thanh địa chỉ ở đầu trang
#   ví dụ: "https://ten-du-an-default-rtdb.asia-southeast1.firebasedatabase.app"
# API_KEY: Firebase Console -> Project settings (bánh răng) -> General -> Web API Key
#   (để trống nếu Rules đang mở hoàn toàn, nhưng KHÔNG nên làm vậy)
DATABASE_URL = "https://esp-bat-default-rtdb.asia-southeast1.firebasedatabase.app"
API_KEY = ""

# Nhánh gốc trong database. Dữ liệu nằm ở: <DB_ROOT>/readings/<key>
DB_ROOT = "udp_receiver"

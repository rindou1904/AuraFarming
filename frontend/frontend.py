import streamlit as st
import requests
from datetime import datetime

# ========== CẤU HÌNH ==========
API_URL = "http://localhost:8000"

st.set_page_config(
    page_title="Quản lý chuỗi cung ứng nông nghiệp",
    page_icon="🌾",
    layout="wide"
)

# Khởi tạo session state
if "token" not in st.session_state:
    st.session_state.token = None
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "role" not in st.session_state:
    st.session_state.role = None

# ========== HÀM GỌI API ==========
def api_call(method, endpoint, data=None, need_auth=True):
    url = f"{API_URL}{endpoint}"
    headers = {}
    
    if need_auth and st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "POST":
            response = requests.post(url, json=data, headers=headers)
        elif method == "PUT":
            response = requests.put(url, json=data, headers=headers)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers)
        
        if response.status_code in [200, 201]:
            return True, response.json()
        else:
            error_msg = response.json().get("detail", "Lỗi không xác định")
            return False, error_msg
    except Exception as e:
        return False, str(e)

# ========== TRANG ĐĂNG NHẬP ==========
def login_page():
    st.title("🌾 Hệ thống quản lý chuỗi cung ứng nông nghiệp")
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.subheader("🔐 Đăng nhập")
        
        username = st.text_input("Tên đăng nhập")
        password = st.text_input("Mật khẩu", type="password")
        
        if st.button("Đăng nhập", use_container_width=True):
            if username and password:
                success, result = api_call("POST", "/login", {"username": username, "password": password}, need_auth=False)
                if success:
                    st.session_state.token = result["access_token"]
                    st.session_state.user_id = result["user_id"]
                    st.session_state.role = result["role"]
                    st.success("Đăng nhập thành công!")
                    st.rerun()
                else:
                    st.error(f"Đăng nhập thất bại: {result}")
            else:
                st.warning("Vui lòng nhập đầy đủ thông tin")
        
        st.markdown("---")
        st.caption("Tài khoản mặc định: admin / admin123")

# ========== TRANG CHÍNH ==========
def main_page():
    # Sidebar
    with st.sidebar:
        st.title(f"👋 Xin chào, {st.session_state.role}")
        
        # Lấy thông tin user
        success, user_info = api_call("GET", "/me")
        if success:
            st.info(f"**{user_info.get('fullname', '')}**\n@{user_info.get('username', '')}")
        
        st.markdown("---")
        
        # Menu
        menu = st.radio(
            "📋 Menu",
            ["🏠 Trang chủ", "📦 Sản phẩm", "🌡️ Cảm biến", "🚚 Chuỗi cung ứng", "📊 Thống kê"]
        )
        
        if st.session_state.role == "admin":
            st.markdown("---")
            if st.button("👥 Quản lý user", use_container_width=True):
                menu = "👥 Quản lý user"
        
        st.markdown("---")
        if st.button("🚪 Đăng xuất", use_container_width=True):
            st.session_state.token = None
            st.session_state.user_id = None
            st.session_state.role = None
            st.rerun()
    
    # Xử lý menu
    if menu == "🏠 Trang chủ":
        dashboard_page()
    elif menu == "📦 Sản phẩm":
        product_page()
    elif menu == "🌡️ Cảm biến":
        sensor_page()
    elif menu == "🚚 Chuỗi cung ứng":
        supply_chain_page()
    elif menu == "📊 Thống kê":
        statistics_page()
    elif menu == "👥 Quản lý user":
        user_management_page()

# ========== DASHBOARD ==========
def dashboard_page():
    st.title("🏠 Bảng điều khiển")
    
    success, stats = api_call("GET", "/statistics")
    if success:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("📦 Tổng sản phẩm", stats.get("total_products", 0))
        with col2:
            st.metric("🌾 Sản phẩm của bạn", stats.get("my_products", 0))
        
        st.info(stats.get("message", ""))
    
    # Hiển thị sản phẩm gần đây
    st.subheader("📦 Danh sách sản phẩm")
    success, products = api_call("GET", "/products?limit=5")
    
    if success and products:
        for product in products:
            with st.container():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**{product['name']}** - {product['origin']}")
                    st.caption(product['description'][:100] if product['description'] else "")
                with col2:
                    st.metric("💰 Giá", f"{product['price']:,.0f} VND")
                st.divider()
    else:
        st.info("Chưa có sản phẩm nào")

# ========== QUẢN LÝ SẢN PHẨM ==========
def product_page():
    st.title("📦 Quản lý sản phẩm")
    
    # Khởi tạo session state
    if "show_edit_form" not in st.session_state:
        st.session_state.show_edit_form = False
    if "edit_product_data" not in st.session_state:
        st.session_state.edit_product_data = None
    
    tab1, tab2 = st.tabs(["➕ Thêm sản phẩm", "📋 Danh sách sản phẩm"])
    
    # Tab Thêm sản phẩm
    with tab1:
        with st.form("add_product_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Tên sản phẩm*")
                description = st.text_area("Mô tả")
            with col2:
                price = st.number_input("Giá (VNĐ/kg)*", min_value=0.0, step=1000.0)
                quantity = st.number_input("Số lượng (kg)*", min_value=0.0, step=0.1)
                origin = st.text_input("Xuất xứ*")
            
            if st.form_submit_button("➕ Thêm sản phẩm"):
                if name and origin and price > 0:
                    success, _ = api_call("POST", "/products", {
                        "name": name, "description": description,
                        "price": price, "quantity": quantity, "origin": origin
                    })
                    if success:
                        st.success("✅ Thêm thành công!")
                        st.rerun()
                    else:
                        st.error("❌ Thêm thất bại")
    
    # Tab Danh sách sản phẩm
    with tab2:
        success, products = api_call("GET", "/products")
        
        if success and products:
            for p in products:
                with st.expander(f"🌾 {p['name']} - {p['origin']}"):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**📝 Mô tả:** {p['description']}")
                        st.write(f"**💰 Giá:** {p['price']:,.0f} VND/kg")
                        st.write(f"**📦 Số lượng:** {p['quantity']} kg")
                        st.write(f"**📅 Ngày tạo:** {p['created_at'][:10] if p.get('created_at') else 'N/A'}")
                    
                    with col2:
                        if st.button("✏️ Sửa", key=f"edit_{p['id']}"):
                            st.session_state.show_edit_form = True
                            st.session_state.edit_product_data = p
                            st.rerun()
                        
                        if st.button("🗑️ Xóa", key=f"delete_{p['id']}"):
                            success, _ = api_call("DELETE", f"/products/{p['id']}")
                            if success:
                                st.success("✅ Xóa thành công!")
                                st.rerun()
                            else:
                                st.error("❌ Xóa thất bại")
        
        # Form sửa sản phẩm (hiển thị khi có sản phẩm được chọn)
        if st.session_state.show_edit_form and st.session_state.edit_product_data:
            p = st.session_state.edit_product_data
            st.markdown("---")
            st.subheader(f"✏️ Sửa sản phẩm: {p['name']}")
            
            with st.form("edit_product_form"):
                col1, col2 = st.columns(2)
                with col1:
                    new_price = st.number_input(
                        "💰 Giá mới (VNĐ/kg)", 
                        value=float(p['price']), 
                        step=1000.0,
                        min_value=0.0
                    )
                with col2:
                    new_quantity = st.number_input(
                        "📦 Số lượng mới (kg)", 
                        value=float(p['quantity']), 
                        step=0.1,
                        min_value=0.0
                    )
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.form_submit_button("💾 Lưu thay đổi"):
                        success, _ = api_call("PUT", f"/products/{p['id']}", {
                            "price": new_price, 
                            "quantity": new_quantity
                        })
                        if success:
                            st.success("✅ Cập nhật thành công!")
                            st.session_state.show_edit_form = False
                            st.session_state.edit_product_data = None
                            st.rerun()
                        else:
                            st.error("❌ Cập nhật thất bại")
                
                with col2:
                    if st.form_submit_button("❌ Hủy"):
                        st.session_state.show_edit_form = False
                        st.session_state.edit_product_data = None
                        st.rerun()
        else:
            st.info("📌 Chọn sản phẩm để sửa")

# ========== CẢM BIẾN ==========
def sensor_page():
    st.title("🌡️ Dữ liệu cảm biến")
    
    success, products = api_call("GET", "/products")
    if success and products:
        product_names = {f"{p['name']}": p['id'] for p in products}
        selected = st.selectbox("Chọn sản phẩm", list(product_names.keys()))
        product_id = product_names[selected]
        
        tab1, tab2 = st.tabs(["➕ Thêm dữ liệu", "📊 Xem dữ liệu"])
        
        with tab1:
            with st.form("add_sensor"):
                col1, col2 = st.columns(2)
                temp = col1.number_input("Nhiệt độ (°C)", value=25.0)
                hum = col2.number_input("Độ ẩm (%)", value=70.0, min_value=0.0, max_value=100.0)
                
                if st.form_submit_button("Ghi nhận"):
                    success, _ = api_call("POST", f"/products/{product_id}/sensor", {
                        "temperature": temp, "humidity": hum
                    })
                    if success:
                        st.success("Đã ghi nhận!")
                        st.rerun()
        
        with tab2:
            success, sensors = api_call("GET", f"/products/{product_id}/sensor")
            if success and sensors:
                for s in sensors[:10]:
                    st.write(f"📅 {s['timestamp'][:19]} | 🌡️ {s['temperature']}°C | 💧 {s['humidity']}%")
            else:
                st.info("Chưa có dữ liệu")

# ========== CHUỖI CUNG ỨNG ==========
def supply_chain_page():
    st.title("🚚 Chuỗi cung ứng")
    
    success, products = api_call("GET", "/products")
    if success and products:
        product_names = {f"{p['name']}": p['id'] for p in products}
        selected = st.selectbox("Chọn sản phẩm", list(product_names.keys()))
        product_id = product_names[selected]
        
        tab1, tab2 = st.tabs(["➕ Thêm sự kiện", "📜 Lịch sử"])
        
        with tab1:
            with st.form("add_event"):
                stage = st.selectbox("Giai đoạn", ["Thu hoạch", "Vận chuyển", "Đóng gói", "Phân phối"])
                location = st.text_input("Địa điểm")
                if st.form_submit_button("Thêm sự kiện"):
                    if location:
                        success, _ = api_call("POST", f"/products/{product_id}/event", {
                            "stage": stage, "location": location
                        })
                        if success:
                            st.success("Đã thêm!")
                            st.rerun()
        
        with tab2:
            success, events = api_call("GET", f"/products/{product_id}/events")
            if success and events:
                for e in events:
                    st.write(f"📅 {e['timestamp'][:19]} | 📍 {e['stage']} | 🏠 {e['location']}")
            else:
                st.info("Chưa có sự kiện")

# ========== THỐNG KÊ ==========
def statistics_page():
    st.title("📊 Thống kê")
    
    success, stats = api_call("GET", "/statistics")
    if success:
        st.metric("📦 Tổng sản phẩm", stats.get("total_products", 0))
        st.metric("🌾 Sản phẩm của bạn", stats.get("my_products", 0))

# ========== QUẢN LÝ USER (ADMIN) ==========
def user_management_page():
    st.title("👥 Quản lý người dùng")
    
    success, users = api_call("GET", "/admin/users")
    if success and users:
        for user in users:
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                st.write(f"**{user['fullname']}**")
            with col2:
                st.write(f"@{user['username']} - {user['role']}")
            with col3:
                if user['role'] != "admin":
                    if st.button("🗑️", key=f"del_{user['id']}"):
                        success, _ = api_call("DELETE", f"/admin/users/{user['id']}")
                        if success:
                            st.success("Đã xóa!")
                            st.rerun()
            st.divider()

# ========== MAIN ==========
if __name__ == "__main__":
    if not st.session_state.token:
        login_page()
    else:
        main_page()
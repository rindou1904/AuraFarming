from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from datetime import datetime, timedelta
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from passlib.context import CryptContext
import jwt

# ========== 1. CẤU HÌNH CƠ BẢN ==========
SQLALCHEMY_DATABASE_URL = "sqlite:///./agriculture.db"
SECRET_KEY = "secret-key-123"  # Khóa bí mật để mã hóa token
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# ========== 2. CÁC BẢNG TRONG DATABASE ==========

# Bảng người dùng
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)  # Mật khẩu đã mã hóa
    fullname = Column(String)
    role = Column(String, default="user")  # "admin" hoặc "user"
    
    # Liên kết đến bảng sản phẩm (1 người có nhiều sản phẩm)
    products = relationship("Product", back_populates="owner")

# Bảng sản phẩm nông nghiệp
class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)          # Tên sản phẩm
    description = Column(String)                # Mô tả
    price = Column(Float)                       # Giá bán
    quantity = Column(Float)                    # Số lượng (kg)
    origin = Column(String)                     # Xuất xứ
    user_id = Column(Integer, ForeignKey("users.id"))  # Người tạo
    created_at = Column(DateTime, default=datetime.utcnow)
    
    owner = relationship("User", back_populates="products")
    sensors = relationship("Sensor", back_populates="product", cascade="all, delete-orphan")
    events = relationship("SupplyChain", back_populates="product", cascade="all, delete-orphan")

# Bảng dữ liệu cảm biến (IoT)
class Sensor(Base):
    __tablename__ = "sensors"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    temperature = Column(Float)   # Nhiệt độ
    humidity = Column(Float)      # Độ ẩm
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    product = relationship("Product", back_populates="sensors")

# Bảng theo dõi chuỗi cung ứng
class SupplyChain(Base):
    __tablename__ = "supply_chain"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    stage = Column(String)        # Giai đoạn: Thu hoạch, Vận chuyển, Đóng gói, Phân phối
    location = Column(String)     # Địa điểm
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    product = relationship("Product", back_populates="events")

# Tạo các bảng trong database
Base.metadata.create_all(bind=engine)

# ========== 3. KHUÔN MẪU DỮ LIỆU (Pydantic) ==========

# User
class UserRegister(BaseModel):
    username: str
    password: str
    fullname: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    fullname: str
    role: str
    model_config = ConfigDict(from_attributes=True)

# Token
class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    role: str

# Product
class ProductCreate(BaseModel):
    name: str
    description: str
    price: float
    quantity: float
    origin: str

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[float] = None

class ProductResponse(BaseModel):
    id: int
    name: str
    description: str
    price: float
    quantity: float
    origin: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# Sensor
class SensorCreate(BaseModel):
    temperature: float
    humidity: float

class SensorResponse(SensorCreate):
    id: int
    product_id: int
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)

# Supply Chain
class SupplyChainCreate(BaseModel):
    stage: str
    location: str

class SupplyChainResponse(SupplyChainCreate):
    id: int
    product_id: int
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)

# ========== 4. HÀM HỖ TRỢ ==========

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Mã hóa mật khẩu
def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str):
    return pwd_context.verify(plain, hashed)

# Tạo token JWT
def create_token(user_id: int, role: str):
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"user_id": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

# Lấy thông tin user từ token
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token không hợp lệ")
    except:
        raise HTTPException(status_code=401, detail="Token không hợp lệ")
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Không tìm thấy user")
    return user

# Kiểm tra quyền admin
def check_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Yêu cầu quyền admin")
    return current_user

# ========== 5. KHỞI TẠO APP ==========
app = FastAPI(title="Quản lý Chuỗi Cung ứng Nông nghiệp", version="1.0")

# Tạo tài khoản admin mặc định nếu chưa có
@app.on_event("startup")
def create_default_admin():
    db = SessionLocal()
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin_user = User(
            username="admin",
            password=hash_password("admin123"),
            fullname="Administrator",
            role="admin"
        )
        db.add(admin_user)
        db.commit()
    db.close()

# ========== 6. API AUTHENTICATION ==========

@app.post("/register", response_model=UserResponse, tags=["Xác thực"])
def register(user: UserRegister, db: Session = Depends(get_db)):
    """Đăng ký tài khoản mới"""
    # Kiểm tra username đã tồn tại chưa
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại")
    
    # Tạo user mới (mặc định role = user)
    new_user = User(
        username=user.username,
        password=hash_password(user.password),
        fullname=user.fullname,
        role="user"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/login", response_model=TokenResponse, tags=["Xác thực"])
def login(user: UserLogin, db: Session = Depends(get_db)):
    """Đăng nhập và nhận token"""
    db_user = db.query(User).filter(User.username == user.username).first()
    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")
    
    token = create_token(db_user.id, db_user.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": db_user.id,
        "role": db_user.role
    }

@app.get("/me", response_model=UserResponse, tags=["Xác thực"])
def get_me(current_user: User = Depends(get_current_user)):
    """Lấy thông tin user hiện tại"""
    return current_user

# ========== 7. API QUẢN LÝ SẢN PHẨM ==========

@app.post("/products", response_model=ProductResponse, tags=["Sản phẩm"])
def create_product(product: ProductCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Thêm sản phẩm mới"""
    db_product = Product(
        **product.model_dump(),
        user_id=current_user.id
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

@app.get("/products", response_model=List[ProductResponse], tags=["Sản phẩm"])
def get_products(
    skip: int = 0, 
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Xem danh sách sản phẩm (admin thấy tất cả, user chỉ thấy sản phẩm của mình)"""
    if current_user.role == "admin":
        products = db.query(Product).offset(skip).limit(limit).all()
    else:
        products = db.query(Product).filter(Product.user_id == current_user.id).offset(skip).limit(limit).all()
    return products

@app.get("/products/{product_id}", response_model=ProductResponse, tags=["Sản phẩm"])
def get_product(product_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Xem chi tiết 1 sản phẩm"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    
    # Kiểm tra quyền
    if current_user.role != "admin" and product.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Không có quyền xem sản phẩm này")
    
    return product

@app.put("/products/{product_id}", response_model=ProductResponse, tags=["Sản phẩm"])
def update_product(product_id: int, product_update: ProductUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Cập nhật sản phẩm"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    
    if current_user.role != "admin" and product.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Không có quyền sửa sản phẩm này")
    
    for key, value in product_update.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    
    db.commit()
    db.refresh(product)
    return product

@app.delete("/products/{product_id}", tags=["Sản phẩm"])
def delete_product(product_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Xóa sản phẩm"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    
    if current_user.role != "admin" and product.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Không có quyền xóa sản phẩm này")
    
    db.delete(product)
    db.commit()
    return {"message": "Xóa sản phẩm thành công"}

# ========== 8. API DỮ LIỆU CẢM BIẾN ==========

@app.post("/products/{product_id}/sensor", response_model=SensorResponse, tags=["Cảm biến"])
def add_sensor_data(product_id: int, sensor: SensorCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Thêm dữ liệu cảm biến cho sản phẩm"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    
    if current_user.role != "admin" and product.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    db_sensor = Sensor(**sensor.model_dump(), product_id=product_id)
    db.add(db_sensor)
    db.commit()
    db.refresh(db_sensor)
    return db_sensor

@app.get("/products/{product_id}/sensor", response_model=List[SensorResponse], tags=["Cảm biến"])
def get_sensor_data(product_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Xem dữ liệu cảm biến của sản phẩm"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    
    if current_user.role != "admin" and product.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    return db.query(Sensor).filter(Sensor.product_id == product_id).order_by(Sensor.timestamp.desc()).all()

# ========== 9. API CHUỖI CUNG ỨNG ==========

@app.post("/products/{product_id}/event", response_model=SupplyChainResponse, tags=["Chuỗi cung ứng"])
def add_event(product_id: int, event: SupplyChainCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Thêm sự kiện vào chuỗi cung ứng"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    
    if current_user.role != "admin" and product.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    db_event = SupplyChain(**event.model_dump(), product_id=product_id)
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event

@app.get("/products/{product_id}/events", response_model=List[SupplyChainResponse], tags=["Chuỗi cung ứng"])
def get_events(product_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Xem toàn bộ chuỗi cung ứng của sản phẩm"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    
    if current_user.role != "admin" and product.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    return db.query(SupplyChain).filter(SupplyChain.product_id == product_id).order_by(SupplyChain.timestamp).all()

# ========== 10. API ADMIN ==========

@app.get("/admin/users", tags=["Admin"])
def get_all_users(admin: User = Depends(check_admin), db: Session = Depends(get_db)):
    """[ADMIN] Xem danh sách tất cả người dùng"""
    users = db.query(User).all()
    return [
        {"id": u.id, "username": u.username, "fullname": u.fullname, "role": u.role}
        for u in users
    ]

@app.delete("/admin/users/{user_id}", tags=["Admin"])
def delete_user(user_id: int, admin: User = Depends(check_admin), db: Session = Depends(get_db)):
    """[ADMIN] Xóa người dùng"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy user")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Không thể xóa chính mình")
    
    db.delete(user)
    db.commit()
    return {"message": f"Đã xóa user {user.username}"}

@app.get("/statistics", tags=["Thống kê"])
def get_statistics(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Thống kê sản phẩm"""
    if current_user.role == "admin":
        products = db.query(Product).all()
        total_products = len(products)
        total_users = db.query(User).count()
    else:
        products = db.query(Product).filter(Product.user_id == current_user.id).all()
        total_products = len(products)
        total_users = None
    
    return {
        "total_products": total_products,
        "total_users": total_users if current_user.role == "admin" else "Chỉ admin mới xem được",
        "my_products": total_products,
        "message": f"Xin chào {current_user.fullname}!"
    }

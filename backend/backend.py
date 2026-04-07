from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import List, Optional
import hashlib
import secrets
import uvicorn

# ========== CẤU HÌNH DATABASE ==========
SQLALCHEMY_DATABASE_URL = "sqlite:///./agriculture.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
security = HTTPBearer()

# ========== HÀM TẠO TOKEN ĐƠN GIẢN ==========
def create_token(user_id: int, role: str):
    """Tạo token đơn giản không cần thư viện jwt"""
    token_data = f"{user_id}|{role}|{secrets.token_hex(16)}"
    return token_data

def verify_token(token: str):
    """Xác thực token"""
    try:
        parts = token.split('|')
        if len(parts) >= 2:
            return {"user_id": int(parts[0]), "role": parts[1]}
    except:
        pass
    return None

# ========== HÀM MÃ HÓA MẬT KHẨU ==========
def hash_password(password: str):
    """Mã hóa mật khẩu đơn giản"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain: str, hashed: str):
    """Kiểm tra mật khẩu"""
    return hash_password(plain) == hashed

# ========== MODELS ==========
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    fullname = Column(String)
    role = Column(String, default="user")
    
    products = relationship("Product", back_populates="owner")

class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, default="")
    price = Column(Float, default=0)
    quantity = Column(Float, default=0)
    origin = Column(String, default="")
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    owner = relationship("User", back_populates="products")
    sensors = relationship("Sensor", back_populates="product", cascade="all, delete-orphan")
    events = relationship("SupplyChain", back_populates="product", cascade="all, delete-orphan")

class Sensor(Base):
    __tablename__ = "sensors"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    temperature = Column(Float, default=0)
    humidity = Column(Float, default=0)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    product = relationship("Product", back_populates="sensors")

class SupplyChain(Base):
    __tablename__ = "supply_chain"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    stage = Column(String, default="")
    location = Column(String, default="")
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    product = relationship("Product", back_populates="events")

# ========== TẠO BẢNG ==========
try:
    Base.metadata.create_all(bind=engine)
    print("✅ Database created successfully!")
except Exception as e:
    print(f"❌ Database error: {e}")

# ========== PYDANTIC SCHEMAS ==========
class UserRegister(BaseModel):
    username: str
    password: str
    fullname: str

class UserLogin(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    role: str

class UserResponse(BaseModel):
    id: int
    username: str
    fullname: str
    role: str

class ProductCreate(BaseModel):
    name: str
    description: str = ""
    price: float = 0
    quantity: float = 0
    origin: str = ""

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

class SensorCreate(BaseModel):
    temperature: float
    humidity: float

class SensorResponse(BaseModel):
    id: int
    product_id: int
    temperature: float
    humidity: float
    timestamp: datetime

class SupplyChainCreate(BaseModel):
    stage: str
    location: str

class SupplyChainResponse(BaseModel):
    id: int
    product_id: int
    stage: str
    location: str
    timestamp: datetime

# ========== DEPENDENCIES ==========
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
    token_data = verify_token(token)
    if not token_data:
        raise HTTPException(status_code=401, detail="Token không hợp lệ")
    
    user = db.query(User).filter(User.id == token_data["user_id"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="Không tìm thấy user")
    return user

def check_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Yêu cầu quyền admin")
    return current_user

# ========== TẠO APP ==========
app = FastAPI(title="Quản lý Chuỗi Cung ứng Nông nghiệp", version="1.0")

# Tạo admin mặc định khi khởi động
@app.on_event("startup")
def create_default_admin():
    try:
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
            print("✅ Admin user created: admin/admin123")
        db.close()
    except Exception as e:
        print(f"⚠️ Could not create admin: {e}")

# ========== AUTH APIS ==========
@app.post("/register", response_model=UserResponse)
def register(user: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại")
    
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

@app.post("/login", response_model=TokenResponse)
def login(user: UserLogin, db: Session = Depends(get_db)):
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

@app.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

# ========== PRODUCT APIS ==========
@app.post("/products", response_model=ProductResponse)
def create_product(product: ProductCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_product = Product(**product.dict(), user_id=current_user.id)
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

@app.get("/products", response_model=List[ProductResponse])
def get_products(skip: int = 0, limit: int = 100, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role == "admin":
        products = db.query(Product).offset(skip).limit(limit).all()
    else:
        products = db.query(Product).filter(Product.user_id == current_user.id).offset(skip).limit(limit).all()
    return products

@app.get("/products/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    if current_user.role != "admin" and product.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Không có quyền")
    return product

@app.put("/products/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, product_update: ProductUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    if current_user.role != "admin" and product.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    update_data = product_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(product, key, value)
    
    db.commit()
    db.refresh(product)
    return product

@app.delete("/products/{product_id}")
def delete_product(product_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    if current_user.role != "admin" and product.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    db.delete(product)
    db.commit()
    return {"message": "Xóa sản phẩm thành công"}

# ========== SENSOR APIS ==========
@app.post("/products/{product_id}/sensor", response_model=SensorResponse)
def add_sensor(product_id: int, sensor: SensorCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    if current_user.role != "admin" and product.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    db_sensor = Sensor(**sensor.dict(), product_id=product_id)
    db.add(db_sensor)
    db.commit()
    db.refresh(db_sensor)
    return db_sensor

@app.get("/products/{product_id}/sensor", response_model=List[SensorResponse])
def get_sensors(product_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    if current_user.role != "admin" and product.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    return db.query(Sensor).filter(Sensor.product_id == product_id).order_by(Sensor.timestamp.desc()).limit(50).all()

# ========== SUPPLY CHAIN APIS ==========
@app.post("/products/{product_id}/event", response_model=SupplyChainResponse)
def add_event(product_id: int, event: SupplyChainCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    if current_user.role != "admin" and product.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    db_event = SupplyChain(**event.dict(), product_id=product_id)
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event

@app.get("/products/{product_id}/events", response_model=List[SupplyChainResponse])
def get_events(product_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    if current_user.role != "admin" and product.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    return db.query(SupplyChain).filter(SupplyChain.product_id == product_id).order_by(SupplyChain.timestamp).all()

# ========== ADMIN APIS ==========
@app.get("/admin/users")
def get_users(admin: User = Depends(check_admin), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [{"id": u.id, "username": u.username, "fullname": u.fullname, "role": u.role} for u in users]

@app.delete("/admin/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(check_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy user")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Không thể xóa chính mình")
    
    db.delete(user)
    db.commit()
    return {"message": f"Đã xóa user {user.username}"}

# ========== STATISTICS API ==========
@app.get("/statistics")
def get_statistics(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role == "admin":
        total_products = db.query(Product).count()
        total_users = db.query(User).count()
    else:
        total_products = db.query(Product).filter(Product.user_id == current_user.id).count()
        total_users = None
    
    return {
        "total_products": total_products,
        "total_users": total_users if current_user.role == "admin" else "Chỉ admin mới xem được",
        "my_products": total_products,
        "message": f"Xin chào {current_user.fullname}!"
    }

# ========== ROOT ENDPOINT ==========
@app.get("/")
def root():
    return {"message": "API đang chạy", "status": "OK"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

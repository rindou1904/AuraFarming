from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import List, Optional

# --- 1. CONFIGURATION & DATABASE ---
# Sử dụng SQLite để lưu trữ cơ sở dữ liệu (file smart_agriculture.db sẽ được tự động tạo)
SQLALCHEMY_DATABASE_URL = "sqlite:///./smart_agriculture.db"

# Cài đặt check_same_thread=False là bắt buộc đối với SQLite khi dùng chung với FastAPI
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 2. SQLALCHEMY MODELS (DATABASE TABLES) ---
class ProductDB(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String)
    origin = Column(String) # Nguồn gốc xuất xứ (trang trại nào, vùng nào)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Thiết lập quan hệ (Relationship) để dễ truy vấn
    sensor_data = relationship("SensorDataDB", back_populates="product", cascade="all, delete-orphan")
    supply_chain_events = relationship("SupplyChainDB", back_populates="product", cascade="all, delete-orphan")

class SensorDataDB(Base):
    __tablename__ = "sensor_data"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    temperature = Column(Float) # Nhiệt độ (độ C) dùng để giám sát môi trường lưu trữ
    humidity = Column(Float)    # Độ ẩm (%)
    recorded_at = Column(DateTime, default=datetime.utcnow)
    
    product = relationship("ProductDB", back_populates="sensor_data")

class SupplyChainDB(Base):
    __tablename__ = "supply_chain_events"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    event_name = Column(String) # Ví dụ: "Thu hoạch", "Đóng gói", "Vận chuyển", "Nhập kho", "Phân phối"
    location = Column(String)   # Địa điểm diễn ra sự kiện
    actor = Column(String)      # Người hoặc tổ chức thực hiện
    recorded_at = Column(DateTime, default=datetime.utcnow)
    
    product = relationship("ProductDB", back_populates="supply_chain_events")

# Tạo các bảng thực tế trong Database SQLite
Base.metadata.create_all(bind=engine)


# --- 3. PYDANTIC MODELS (SCHEMAS FOR API INPUT/OUTPUT) ---
# Dùng để kiểm tra tính hợp lệ của dữ liệu đầu vào và format đầu ra

class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    origin: str

class ProductCreate(ProductBase):
    pass

class ProductResponse(ProductBase):
    id: int
    created_at: datetime
    # Cấu hình để Pydantic có thể đọc được dữ liệu trực tiếp từ các object Database của SQLAlchemy
    model_config = ConfigDict(from_attributes=True) 

class SensorDataCreate(BaseModel):
    temperature: float
    humidity: float

class SensorDataResponse(SensorDataCreate):
    id: int
    product_id: int
    recorded_at: datetime
    model_config = ConfigDict(from_attributes=True)

class SupplyChainCreate(BaseModel):
    event_name: str
    location: str
    actor: str

class SupplyChainResponse(SupplyChainCreate):
    id: int
    product_id: int
    recorded_at: datetime
    model_config = ConfigDict(from_attributes=True)


# --- 4. CẤU HÌNH FASTAPI APP ---
app = FastAPI(
    title="Hệ thống quản lý chuỗi cung ứng Nông nghiệp Thông minh (Smart Agriculture Supply Chain API)",
    description="API giúp theo dõi nông sản, giám sát dữ liệu môi trường từ thiết bị IoT và truy xuất nguồn gốc trong chuỗi cung ứng.",
    version="1.0.0"
)

# Hàm Dependency dùng để mở và đóng kết nối Database an toàn cho mỗi request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# === CÁC API ENDPOINTS ===

# --- API Nông sản (Products) ---
@app.post("/products", response_model=ProductResponse, tags=["Nông sản (Products)"])
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    """Đăng ký một lô nông sản / cây trồng mới vào hệ thống"""
    db_product = ProductDB(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

@app.get("/products", response_model=List[ProductResponse], tags=["Nông sản (Products)"])
def get_products(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    """Lấy danh sách các nông sản đang được quản lý"""
    return db.query(ProductDB).offset(skip).limit(limit).all()

@app.get("/products/{product_id}", response_model=ProductResponse, tags=["Nông sản (Products)"])
def get_product(product_id: int, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết của một nông sản thông qua ID"""
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy nông sản")
    return product


# --- API Dữ liệu cảm biến IoT (Sensor Data) ---
@app.post("/products/{product_id}/sensor-data", response_model=SensorDataResponse, tags=["Dữ liệu cảm biến (IoT)"])
def add_sensor_data(product_id: int, sensor_data: SensorDataCreate, db: Session = Depends(get_db)):
    """Ghi nhận dữ liệu độ ẩm, nhiệt độ môi trường cho lô nông sản (từ thiết bị IoT)"""
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy nông sản")
        
    db_sensor = SensorDataDB(**sensor_data.model_dump(), product_id=product_id)
    db.add(db_sensor)
    db.commit()
    db.refresh(db_sensor)
    return db_sensor

@app.get("/products/{product_id}/sensor-data", response_model=List[SensorDataResponse], tags=["Dữ liệu cảm biến (IoT)"])
def get_sensor_data_by_product(product_id: int, db: Session = Depends(get_db)):
    """Xem lịch sử dữ liệu cảm biến của một lô nông sản"""
    return db.query(SensorDataDB).filter(SensorDataDB.product_id == product_id).order_by(SensorDataDB.recorded_at.desc()).all()


# --- API Truy xuất chuỗi cung ứng (Supply Chain tracking) ---
@app.post("/products/{product_id}/supply-chain-events", response_model=SupplyChainResponse, tags=["Chuỗi cung ứng (Supply Chain)"])
def add_supply_chain_event(product_id: int, event: SupplyChainCreate, db: Session = Depends(get_db)):
    """Cập nhật trạng thái chuỗi cung ứng (VD: Đã thu hoạch, Đang vận chuyển, Nhập kho...)"""
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy nông sản")
        
    db_event = SupplyChainDB(**event.model_dump(), product_id=product_id)
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event

@app.get("/products/{product_id}/supply-chain-events", response_model=List[SupplyChainResponse], tags=["Chuỗi cung ứng (Supply Chain)"])
def get_supply_chain_events(product_id: int, db: Session = Depends(get_db)):
    """Truy xuất nhật ký các sự kiện diễn ra đối với lô nông sản từ lúc tạo đến lúc phân phối"""
    return db.query(SupplyChainDB).filter(SupplyChainDB.product_id == product_id).order_by(SupplyChainDB.recorded_at.asc()).all()

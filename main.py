from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from database import query
from fastapi.middleware.cors import CORSMiddleware
import os
import uuid
from PIL import Image
from fastapi.staticfiles import StaticFiles

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],  # your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
UPLOAD_DIR = "uploads/logos"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class LoginRequest(BaseModel):
    password: str
    
class ResetPasswordRequest(BaseModel):
    current_password: str
    new_password: str

@app.get("/setup", status_code=200)
def setup():
    query("""
        CREATE TABLE IF NOT EXISTS credentials (
            id INT AUTO_INCREMENT PRIMARY KEY,
            password VARCHAR(255) NOT NULL,
            createdate DATETIME DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'active'
        )
    """)

    query("""
        CREATE TABLE IF NOT EXISTS clients (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            phone VARCHAR(20),
            location VARCHAR(255) NOT NULL,
            description VARCHAR(255),
            logo VARCHAR(255),
            createdate DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # query("""
    #     CREATE TABLE IF NOT EXISTS orders (
    #         id INT AUTO_INCREMENT PRIMARY KEY,
    #         client_id INT,
    #         amount DECIMAL(10, 2),
    #         createdate DATETIME DEFAULT CURRENT_TIMESTAMP,
    #         FOREIGN KEY (client_id) REFERENCES clients(id)
    #     )
    # """)

    # Seed default password if DB is fresh
    existing = query("SELECT COUNT(*) as count FROM credentials", fetchone=True)
    if existing["count"] == 0:
        query(
            "INSERT INTO credentials (password, status) VALUES (%s, 'active')",
            ("alwajud2024",)
        )

    return {"message": "Database setup complete"}

@app.post("/login", status_code=200)
def login(body: LoginRequest):
    row = query(
        "SELECT * FROM credentials where status = 'active'",
        fetchone=True
    )

    if not row:
        raise HTTPException(status_code=404, detail="No credentials found")

    if body.password == row["password"]:
        return {"message": "Login successful"}
    else:
        raise HTTPException(status_code=401, detail="Invalid password")
    

@app.post("/resetPassword", status_code=200)
def resetPassword(body: ResetPasswordRequest):
    # Check current password is correct before allowing reset
    row = query(
        "SELECT * FROM credentials WHERE status = 'active'",
        fetchone=True
    )

    if not row:
        raise HTTPException(status_code=404, detail="No active credentials found")

    if body.current_password != row["password"]:
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    # Set all to inactive
    query("UPDATE credentials SET status = 'inactive'")

    # Insert new active password
    query(
        "INSERT INTO credentials (password, status) VALUES (%s, 'active')",
        (body.new_password,)
    )

    return {"message": "Password reset successful"}
    
@app.post("/client", status_code=201)
async def create_client(
    name: str = Form(...),
    phone: str = Form(None),
    location: str = Form(...),
    description: str = Form(None),
    logo: UploadFile = File(None),
):
    logo_filename = None

    if logo:
        if not logo.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")

        ext = logo.filename.split(".")[-1]
        logo_filename = f"{uuid.uuid4()}.{ext}"
        filepath = os.path.join(UPLOAD_DIR, logo_filename)

        image = Image.open(logo.file)
        image.thumbnail((300, 300))
        image.save(filepath)

    query(
        """INSERT INTO clients (name, phone, location, description, logo) 
           VALUES (%s, %s, %s, %s, %s)""",
        (name, phone, location, description, logo_filename)
    )

    return {"message": "Client created"}

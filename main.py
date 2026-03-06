from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from database import query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],  # your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LoginRequest(BaseModel):
    password: str
    
class ResetPasswordRequest(BaseModel):
    current_password: str
    new_password: str

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
    
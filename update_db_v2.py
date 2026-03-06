from app import app, db
from sqlalchemy import text

def update_schema():
    with app.app_context():
        try:
            print("Actualizando tabla 'user'...")
            db.session.execute(text("ALTER TABLE user ADD COLUMN phone VARCHAR(20);"))
            db.session.execute(text("ALTER TABLE user ADD COLUMN address TEXT;"))
            
            print("Actualizando tabla 'order'...")
            db.session.execute(text("ALTER TABLE `order` ADD COLUMN user_id INTEGER;"))
            db.session.execute(text("ALTER TABLE `order` ADD CONSTRAINT fk_order_user FOREIGN KEY (user_id) REFERENCES user(id);"))
            
            db.session.commit()
            print("SUCCESS: Esquema actualizado correctamente.")
        except Exception as e:
            db.session.rollback()
            print(f"ERROR: No se pudo actualizar el esquema: {str(e)}")

if __name__ == "__main__":
    update_schema()

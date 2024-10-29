from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('episodes', sa.Column('created_at', sa.DateTime(), nullable=True))
    
    # Mettre à jour les enregistrements existants
    op.execute("""
        UPDATE episodes 
        SET created_at = CURRENT_TIMESTAMP 
        WHERE created_at IS NULL
    """) 
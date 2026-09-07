"""phase_6_1g_business_data_knowledge

Revision ID: 61gbizdata01
Revises: 5066dcbc0b43
Create Date: 2026-09-06 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '61gbizdata01'
down_revision: Union[str, None] = '5066dcbc0b43'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Business profiles extensions
    op.add_column('business_profiles', sa.Column('email', sa.String(length=255), nullable=True))
    op.add_column('business_profiles', sa.Column('website', sa.String(length=255), nullable=True))
    op.add_column('business_profiles', sa.Column('city', sa.String(length=100), nullable=True))
    op.add_column('business_profiles', sa.Column('province', sa.String(length=100), nullable=True))
    op.add_column('business_profiles', sa.Column('country', sa.String(length=100), nullable=True))
    op.add_column('business_profiles', sa.Column('bank_accounts', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('business_profiles', sa.Column('courier_methods', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('business_profiles', sa.Column('contact_admin_info', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # 2. Products extensions
    op.add_column('products', sa.Column('type', sa.String(length=50), server_default='PRODUCT', nullable=False))
    op.add_column('products', sa.Column('category', sa.String(length=100), nullable=True))
    op.add_column('products', sa.Column('currency', sa.String(length=10), server_default='IDR', nullable=False))
    op.add_column('products', sa.Column('stock_status', sa.String(length=50), server_default='IN_STOCK', nullable=True))
    op.add_column('products', sa.Column('unit', sa.String(length=50), server_default='pcs', nullable=True))

    # 3. Create product_variants table
    op.create_table(
        'product_variants',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('sku', sa.String(length=100), nullable=True),
        sa.Column('price_override', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('stock', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('stock >= 0', name='check_product_variant_stock_non_negative'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_product_variants_tenant_sku', 'product_variants', ['tenant_id', 'sku'], unique=False)
    op.create_index(op.f('ix_product_variants_product_id'), 'product_variants', ['product_id'], unique=False)
    op.create_index(op.f('ix_product_variants_tenant_id'), 'product_variants', ['tenant_id'], unique=False)

    # 4. Create knowledge_items table
    op.create_table(
        'knowledge_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('category_key', sa.String(length=100), server_default='OTHER', nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='DRAFT', nullable=False),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column('owner', sa.String(length=255), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('effective_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expiry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approval_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['approval_id'], ['approvals.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_knowledge_items_tenant_cat', 'knowledge_items', ['tenant_id', 'category_key'], unique=False)
    op.create_index('idx_knowledge_items_tenant_status', 'knowledge_items', ['tenant_id', 'status'], unique=False)
    op.create_index(op.f('ix_knowledge_items_tenant_id'), 'knowledge_items', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_knowledge_items_tenant_id'), table_name='knowledge_items')
    op.drop_index('idx_knowledge_items_tenant_status', table_name='knowledge_items')
    op.drop_index('idx_knowledge_items_tenant_cat', table_name='knowledge_items')
    op.drop_table('knowledge_items')

    op.drop_index(op.f('ix_product_variants_tenant_id'), table_name='product_variants')
    op.drop_index(op.f('ix_product_variants_product_id'), table_name='product_variants')
    op.drop_index('idx_product_variants_tenant_sku', table_name='product_variants')
    op.drop_table('product_variants')

    op.drop_column('products', 'unit')
    op.drop_column('products', 'stock_status')
    op.drop_column('products', 'currency')
    op.drop_column('products', 'category')
    op.drop_column('products', 'type')

    op.drop_column('business_profiles', 'contact_admin_info')
    op.drop_column('business_profiles', 'courier_methods')
    op.drop_column('business_profiles', 'bank_accounts')
    op.drop_column('business_profiles', 'country')
    op.drop_column('business_profiles', 'province')
    op.drop_column('business_profiles', 'city')
    op.drop_column('business_profiles', 'website')
    op.drop_column('business_profiles', 'email')

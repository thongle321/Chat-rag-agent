"""Products admin API — CRUD + CSV import + Shopify sync (both supported)."""

from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.models.unified import Product
from app.services.products import list_products, parse_csv, search_products, upsert_products
from app.services.user_manager import current_admin_user

router = APIRouter()


class ProductUpsert(BaseModel):
    name: str
    description: str | None = None
    price: float | None = None
    currency: str = "USD"
    image_url: str | None = None
    product_url: str | None = None
    category: str | None = None
    stock: int = 0
    sku: str | None = None
    is_active: bool = True


class ShopifySyncRequest(BaseModel):
    shop_domain: str
    access_token: str


@router.get("/")
async def admin_list(user=current_admin_user):
    return {"products": await list_products(active_only=False)}


@router.get("/search")
async def public_search(q: str, k: int = 6):
    """Public product search for chat fallback (anonymous like ChatGPT)."""
    return {"products": await search_products(q, k)}


@router.post("/")
async def create_product(body: ProductUpsert, db: AsyncSession = Depends(get_async_session), user=current_admin_user):
    p = Product(**body.model_dump(), source="manual")
    db.add(p)
    await db.commit()
    await db.refresh(p)
    from app.services.products import to_dict

    return to_dict(p)


@router.put("/{pid}")
async def update_product(
    pid: str, body: ProductUpsert, db: AsyncSession = Depends(get_async_session), user=current_admin_user
):
    p = (await db.execute(select(Product).where(Product.id == pid))).scalar_one_or_none()
    if not p:
        from fastapi import HTTPException

        raise HTTPException(404, "Product not found")
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    await db.commit()
    from app.services.products import to_dict

    return to_dict(p)


@router.delete("/{pid}")
async def delete_product(pid: str, db: AsyncSession = Depends(get_async_session), user=current_admin_user):
    p = (await db.execute(select(Product).where(Product.id == pid))).scalar_one_or_none()
    if p:
        await db.delete(p)
        await db.commit()
    return {"ok": True}


@router.post("/import-csv")
async def import_csv(file: UploadFile, db: AsyncSession = Depends(get_async_session), user=current_admin_user):
    content = (await file.read()).decode("utf-8-sig")
    items = parse_csv(content)
    n = await upsert_products(items, db)
    return {"imported": n}


@router.post("/sync-shopify")
async def sync_shopify(
    body: ShopifySyncRequest, db: AsyncSession = Depends(get_async_session), user=current_admin_user
):
    from app.services.products import ShopifySource, sync_source

    n = await sync_source(ShopifySource(body.shop_domain, body.access_token), db)
    return {"synced": n}

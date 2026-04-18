from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_async_session
from app.core.user import current_superuser, current_user
from app.models.donation import Donation
from app.models.user import User
from app.schemas.donation import (
    DonationCreate,
    DonationDB,
    DonationForUser,
    DonationFullInfoDB,
)
from app.services.investment import process_investment

router = APIRouter()


@router.get('/my', response_model=List[DonationForUser])
async def get_my_donations(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_user),
):
    """Показать пожертвования текущего пользователя."""
    result = await session.execute(
        select(Donation)
        .where(Donation.user_id == user.id)
        .order_by(Donation.create_date)
    )
    return result.scalars().all()


@router.get('/', response_model=List[DonationFullInfoDB])
async def get_all_donations(
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(current_superuser),
):
    """Показать список всех пожертвований (только суперпользователь)."""
    result_all_donations = await session.execute(
        select(Donation).order_by(Donation.create_date)
    )
    return result_all_donations.scalars().all()


@router.post('/', response_model=DonationDB)
async def create_donation(
    donation_in: DonationCreate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_user),
):
    """Создать пожертвование."""
    donation = Donation(
        full_amount=donation_in.full_amount,
        comment=donation_in.comment,
        user_id=user.id,
    )
    session.add(donation)
    await session.flush()

    await process_investment(session)

    await session.refresh(donation)
    return donation

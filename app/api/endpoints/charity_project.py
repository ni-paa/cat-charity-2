from datetime import datetime
from http import HTTPStatus
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_async_session
from app.core.user import current_superuser
from app.models.charity_project import CharityProject
from app.models.user import User
from app.schemas.charity_project import (
    CharityProjectCreate,
    CharityProjectDB,
    CharityProjectUpdate,
)
from app.services.investment import process_investment

router = APIRouter()

_DELETE_FORBIDDEN = 'В проект были внесены средства, не подлежит удалению!'


@router.get('/', response_model=List[CharityProjectDB])
async def get_all_charity_projects(
    session: AsyncSession = Depends(get_async_session),
):
    """Показать список всех целевых проектов."""
    result_all_project = await session.execute(
        select(CharityProject).order_by(CharityProject.create_date)
    )
    return result_all_project.scalars().all()


@router.post('/', response_model=CharityProjectDB)
async def create_charity_project(
    project_in: CharityProjectCreate,
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(current_superuser),
):
    """Создать целевой проект."""
    result = await session.execute(
        select(CharityProject).where(CharityProject.name == project_in.name)
    )
    if result.scalars().first():
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Проект с таким именем уже существует!',
        )
    project = CharityProject(
        name=project_in.name,
        description=project_in.description,
        full_amount=project_in.full_amount,
    )
    session.add(project)
    await session.flush()

    await process_investment(session)

    await session.refresh(project)
    return project


@router.patch('/{project_id}', response_model=CharityProjectDB)
async def update_charity_project(
    project_id: int,
    project_in: CharityProjectUpdate,
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(current_superuser),
):
    """Редактировать целевой проект."""
    project = await session.get(CharityProject, project_id)
    if not project:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Проект не найден',
        )
    if project.fully_invested:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Закрытый проект нельзя редактировать!',
        )

    if project_in.name is not None and project_in.name != project.name:
        result = await session.execute(
            select(CharityProject).where(
                CharityProject.name == project_in.name,
                CharityProject.id != project_id,
            )
        )
        if result.scalars().first():
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Проект с таким именем уже существует!',
            )

    if (
        project_in.full_amount is not None
        and project_in.full_amount < project.invested_amount
    ):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=(
                'Нелья установить значение full_amount '
                'меньше уже вложенной суммы.'
            ),
        )

    if project_in.name is not None:
        project.name = project_in.name
    if project_in.description is not None:
        project.description = project_in.description
    if project_in.full_amount is not None:
        project.full_amount = project_in.full_amount
        if project.invested_amount >= project.full_amount:
            project.fully_invested = True
            project.close_date = datetime.now()

    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.delete('/{project_id}', response_model=CharityProjectDB)
async def delete_charity_project(
    project_id: int,
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(current_superuser),
):
    """Удалить целевой проект."""
    project = await session.get(CharityProject, project_id)
    if not project:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Проект не найден',
        )
    if project.fully_invested or project.invested_amount > 0:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=_DELETE_FORBIDDEN,
        )

    await session.delete(project)
    await session.commit()
    return project

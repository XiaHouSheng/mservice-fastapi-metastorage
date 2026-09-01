from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.database import init_db
from app.utils.logger import setup_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库，关闭时清理资源。"""
    logger = setup_logger()
    logger.info("正在启动 %s v%s (env=%s)", settings.APP_NAME, settings.APP_VERSION, settings.APP_ENV)
    logger.info("user-service 对接地址: %s", settings.USER_SERVICE_URL)
    await init_db()
    logger.info("数据库初始化完成")
    try:
        yield
    finally:
        logger.info("应用已关闭")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="基于 FastAPI 的元数据存储微服务，提供通用结构化元数据的类型管理、实体 CRUD、版本控制与查询检索。",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # 路由
    app.include_router(api_router)

    # 健康检查
    @app.get("/health", tags=["系统"], summary="健康检查")
    async def health_check() -> dict[str, str]:
        return {"status": "healthy", "service": settings.APP_NAME, "version": settings.APP_VERSION}

    @app.get("/", tags=["系统"], summary="服务信息")
    async def root() -> dict[str, str]:
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/docs",
            "health": "/health",
        }

    return app


app = create_app()

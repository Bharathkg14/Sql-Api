import logging
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import py_eureka_client.eureka_client as eureka_client
import asyncio

from app.logger import init_logger
from app.routes import router
from app.settings import settings
from app.utils import gen_props

logger = logging.getLogger(__name__)

# Eureka client configuration
EUREKA_CONFIG = {
    "eureka_server": settings.EUREKA_SERVER_URL,
    "app_name": settings.SERVICE_NAME,
    "instance_host": settings.SERVICE_HOST,
    "instance_port": settings.SERVICE_PORT,
    "health_check_url": f"{settings.API_PROTOCOL}://{settings.SERVICE_HOST}:{settings.SERVICE_PORT}/health",
    "status_page_url": f"{settings.API_PROTOCOL}://{settings.SERVICE_HOST}:{settings.SERVICE_PORT}/info",
    "home_page_url": f"{settings.API_PROTOCOL}://{settings.SERVICE_HOST}:{settings.SERVICE_PORT}/",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    start_time = time.perf_counter()

    # Startup
    logger.info("Starting FastAPI service",
                extra=gen_props(
                    operation="service-startup",
                    eureka_server=EUREKA_CONFIG["eureka_server"],
                    app_name=EUREKA_CONFIG["app_name"]
                ))

    # Register with Eureka server
    try:
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: eureka_client.init(
                eureka_server=EUREKA_CONFIG["eureka_server"],
                app_name=EUREKA_CONFIG["app_name"],
                instance_host=EUREKA_CONFIG["instance_host"],
                instance_port=EUREKA_CONFIG["instance_port"],
                health_check_url=EUREKA_CONFIG["health_check_url"],
                status_page_url=EUREKA_CONFIG["status_page_url"],
                home_page_url=EUREKA_CONFIG["home_page_url"],
            )
        )
        execution_time = time.perf_counter() - start_time

        logger.info("Successfully registered with Eureka server",
                    extra=gen_props(
                        operation="eureka-registration",
                        execution_time=execution_time,
                        eureka_server=EUREKA_CONFIG["eureka_server"],
                        app_name=EUREKA_CONFIG["app_name"],
                        instance=f"{EUREKA_CONFIG['instance_host']}:{EUREKA_CONFIG['instance_port']}"
                    ))
    except Exception as e:
        execution_time = time.perf_counter() - start_time
        logger.error("Failed to register with Eureka server",
                     extra=gen_props(
                         operation="eureka-registration",
                         execution_time=execution_time,
                         error_type="EurekaRegistrationError",
                         error_message=str(e)
                     ))
        logger.warning("Service will continue without Eureka registration",
                       extra=gen_props(
                           operation="eureka-registration",
                           execution_time=execution_time
                       ))

    yield

    # Shutdown
    start_time = time.perf_counter()
    logger.info("Shutting down FastAPI service",
                extra=gen_props(
                    operation="service-shutdown",
                    app_name=EUREKA_CONFIG["app_name"]
                ))


    try:
        eureka_client.stop()
        execution_time = time.perf_counter() - start_time
        logger.info("Successfully deregistered from Eureka server",
                    extra=gen_props(
                        operation="eureka-deregistration",
                        execution_time=execution_time,
                        app_name=EUREKA_CONFIG["app_name"]
                    ))
    except Exception as e:
        execution_time = time.perf_counter() - start_time
        logger.error("Error during Eureka deregistration",
                     extra=gen_props(
                         operation="eureka-deregistration",
                         execution_time=execution_time,
                         error_type="EurekaDeregistrationError",
                         error_message=str(e)
                     ))


app = FastAPI(
    title=settings.TITLE,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
    lifespan=lifespan
)

# Initialize logger
init_logger(app)

# Configure middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint (required for Eureka)
@app.get("/health")
async def health_check():
    """Health check endpoint for Eureka and load balancers"""
    return {
        "status": "UP",
        "service": settings.TITLE,
        "version": settings.VERSION,
        "timestamp": "2024-01-01T00:00:00Z"  # You can use datetime.utcnow().isoformat()
    }


# Service info endpoint
@app.get("/info")
async def service_info():
    """Service information endpoint"""
    return {
        "app": {
            "name": settings.TITLE,
            "version": settings.VERSION,
            "description": settings.DESCRIPTION
        },
        "eureka": {
            "instance": EUREKA_CONFIG["app_name"],
            "host": EUREKA_CONFIG["instance_host"],
            "port": EUREKA_CONFIG["instance_port"]
        }
    }


# Include routers
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
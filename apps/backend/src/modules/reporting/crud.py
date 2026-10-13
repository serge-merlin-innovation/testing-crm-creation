from fastcrud import FastCRUD

from .models import DealForecast

crud_deal_forecast: FastCRUD = FastCRUD(DealForecast)

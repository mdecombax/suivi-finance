# Suivi Finance - Project Instructions for Claude

## Project Overview
Suivi Finance is a Flask-based financial portfolio tracking application that helps users manage investment portfolios with real-time pricing, performance analytics, and tax scenario calculations.

## Key Features
- **Portfolio Management**: Track investment orders with ISIN codes
- **Real-time Pricing**: Integration with Yahoo Finance and JustETF APIs
- **Performance Analytics**: XIRR (money-weighted return) calculations
- **Tax Scenarios**: Support for CTO (30% flat tax) and PEA (17.5% CSG/CRDS) accounts
- **Currency Conversion**: Automatic EUR conversion for international assets
- **Data Persistence**: JSON-based local storage

## Technical Stack
- **Backend**: Flask (Python) with CORS enabled
- **Frontend**: HTML templates with static CSS/JS assets
- **APIs**: Yahoo Finance, JustETF for price data
- **Storage**: Local JSON file (`orders.json`)
- **Environment**: Python virtual environment (`venv/`)

## Project Structure
```
/suivi-finance/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── package.json       # Node.js configuration
├── orders.json        # Data storage file
├── venv/             # Python virtual environment
├── templates/        # HTML templates
│   └── index.html    # Main application page
└── static/           # Static assets
    ├── css/
    ├── js/
    └── img/
```

## Development Commands

### Starting the Application
```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies (if needed)
pip install -r requirements.txt

# Run the application
python app.py
```

The application runs on `http://localhost:5050`

### API Endpoints
- `GET /health` - Health check
- `GET /api/orders` - Retrieve all orders
- `POST /api/orders` - Add new order
- `DELETE /api/orders/<order_id>` - Delete order
- `GET /api/price/<isin>` - Get current price for ISIN
- `GET /api/historical_prices/<isin>` - Get historical prices
- `GET /api/xirr` - Calculate portfolio XIRR

## Important Considerations

### Security
- Never commit API keys or sensitive data
- The application uses local storage - no cloud database
- CORS is enabled for all origins (consider restricting in production)

### Data Handling
- All portfolio data is stored in `orders.json`
- Prices are fetched in real-time from external APIs
- Currency conversion is automatic for non-EUR assets

### Error Handling
- The app includes error handling for API failures
- Fallback mechanisms exist for price fetching (Yahoo Finance → JustETF)

## Common Tasks

### Adding New Features
1. Check existing code patterns in `app.py`
2. Follow Flask route conventions
3. Update frontend in `templates/index.html` if needed
4. Test with sample ISIN codes (e.g., FR0013412285 for S&P 500 ETF)

### Debugging
- Check Flask console for server-side errors
- Use browser developer tools for frontend issues
- Verify `orders.json` format if data issues occur

### Testing
- No automated tests currently exist
- Manual testing through the web interface
- Test with various ISIN codes and date ranges

## Code Style Guidelines
- Follow PEP 8 for Python code
- Use meaningful variable names
- Add docstrings for new functions
- Keep API responses consistent with existing format

## Performance Considerations
- Price fetching can be slow for multiple ISINs
- Consider caching for frequently accessed data
- XIRR calculations may be intensive for large portfolios

## Future Enhancements to Consider
- User authentication system
- Database integration (PostgreSQL/MySQL)
- Automated testing suite
- Docker containerization
- Real-time price updates via WebSocket
- Export functionality (CSV/PDF reports)
- Mobile-responsive design improvements

## Troubleshooting
- **Virtual environment issues**: Recreate with `python -m venv venv`
- **Module import errors**: Check `requirements.txt` and reinstall
- **Price fetch failures**: Verify ISIN codes and API availability
- **CORS errors**: Check Flask-CORS configuration in `app.py`

## Data Format
Orders in `orders.json` follow this structure:
```json
{
  "id": "unique_id",
  "isin": "FR0013412285",
  "quantity": 10,
  "date": "2024-01-15",
  "price": 450.50,
  "type": "buy/sell"
}
```

## Notes for Development
- The application is currently not connected to any Git repository
- Firebase configuration exists but is not actively used
- The frontend could benefit from a modern framework (React/Vue)
- Consider implementing user sessions for multi-user support
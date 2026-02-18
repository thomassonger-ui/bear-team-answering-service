import os
from waitress import serve
from bear_team_phone_system import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"Starting server on port {port}")
    serve(app, host='0.0.0.0', port=port)

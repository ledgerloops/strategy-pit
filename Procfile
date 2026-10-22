release: python app/hosted_release.py
web: gunicorn --chdir app --workers 2 --threads 4 --bind 0.0.0.0:$PORT --timeout 45 'hosted_server:create_app()'
worker: python app/hosted_worker.py

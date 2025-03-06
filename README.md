quick n dirty dockerized audio conversion with ffmpeg.

To start the server:
```source myenv/bin/activate```
```python3 -m uvicorn app.main:app --reload --log-level debug --host 0.0.0.0 --workers 4```




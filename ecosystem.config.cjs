module.exports = {
  apps: [
    {
      name: "musiclounge",
      script: "/volume1/web/MusicLounge/.venv/bin/gunicorn",
      args: "-w 2 --threads 4 --worker-class gthread -b 0.0.0.0:8679 app:app",
      cwd: "/volume1/web/MusicLounge",
      interpreter: "none",
      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};

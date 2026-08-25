"""
MusicLounge Jukebox for Plex — app entrypoint.

Route map (per scope doc):
  /                    home — "Start a Room" / "Share Some Music"
  /admin/login         shared admin auth
  /admin/dashboard     Room Mode host view (player + session control)
  /admin/share         Share Mode admin flow (what / which / how-long)
  /join                Mode A guest join (QR/code -> room)
  /guest               Mode A guest portal (search/browse/queue)
  /linked/<token>      Mode B recipient view — locked single-item player
"""
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
import config


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["SESSION_COOKIE_SECURE"] = config.COOKIE_SECURE

    # Trust one hop of X-Forwarded-Proto/Host from cloudflared, so
    # request.host_url and url_for(_external=True) correctly produce
    # https://musiclounge.vp-fun.com/... (not http://localhost:8679/...)
    # once traffic is flowing through the tunnel. Harmless for direct
    # localhost access — those headers just won't be present, and
    # ProxyFix falls back to the real request info.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    from blueprints.home import bp as home_bp
    from blueprints.admin import bp as admin_bp
    from blueprints.room import bp as room_bp
    from blueprints.share import bp as share_bp
    from blueprints.linked import bp as linked_bp

    app.register_blueprint(home_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(room_bp)
    app.register_blueprint(share_bp, url_prefix="/admin/share")
    app.register_blueprint(linked_bp, url_prefix="/linked")

    @app.after_request
    def no_store(response):
        # RiderMusic hit this exact class of bug (see its own project
        # synopsis) — without a default, a browser or intermediate proxy
        # can cache a GET response like /api/room-state, and every
        # subsequent poll just replays the same stale snapshot forever.
        # Only applies where a route hasn't already set its own
        # Cache-Control (e.g. /art's long-lived cache — album art for a
        # given rating_key never changes, so that one should be cached).
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT)

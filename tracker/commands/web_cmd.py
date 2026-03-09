def cmd_web(args):
    from ..web.server import start_server
    host = getattr(args, "host", "localhost") or "localhost"
    port = getattr(args, "port", 8080) or 8080
    start_server(host=host, port=int(port))

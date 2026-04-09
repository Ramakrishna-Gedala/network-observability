##! NetWatch local Zeek policy.
##!
##! Loaded by `zeek` at runtime via the entrypoint. Enables JSON logging,
##! a short rotation interval (dev-friendly), and the default protocol
##! analyzers that produce conn.log / dns.log / http.log / ssl.log.

@load base/protocols/conn
@load base/protocols/dns
@load base/protocols/http
@load base/protocols/ssl
@load base/frameworks/logging

# Emit logs as one JSON object per line (required by Filebeat input).
redef LogAscii::use_json = T;

# Rotate frequently in dev so Filebeat picks up fresh files quickly.
redef Log::default_rotation_interval = 60 secs;

# Keep logs in the mounted /logs volume.
redef Log::default_logdir = "/logs";

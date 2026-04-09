# Use the upstream Zeek LTS image — avoids the OpenSUSE build-service
# apt repo, which periodically shifts paths and breaks `apt-get update`.
FROM zeek/zeek:lts

USER root
RUN apt-get update && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r netwatch && useradd -r -g netwatch -d /home/netwatch -m netwatch \
    && mkdir -p /logs /pcap /zeek-config \
    && chown -R netwatch:netwatch /logs /pcap /zeek-config

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV PATH="/opt/zeek/bin:${PATH}"

USER netwatch
WORKDIR /logs

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]

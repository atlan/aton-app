ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/aton

# Alles aus Debian-Paketen — kein pip, also kein Compiler und keine Netzabhaengigkeit
# zur Bauzeit ausser dem Paketspiegel. fonts-spleen/xfonts-terminus liefern echte
# Pixel-Schriften als PCF; die werden unten einmalig in Pillows Format uebersetzt.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 \
      python3-pil \
      python3-aiohttp \
      python3-yaml \
      python3-jinja2 \
      python3-ruamel.yaml \
      fonts-spleen \
      xfonts-terminus \
 && rm -rf /var/lib/apt/lists/*

COPY tools/ /tmp/tools/
COPY fonts_src/ /tmp/fonts_src/
COPY panel/builtin_font.py /tmp/panel/builtin_font.py
RUN python3 /tmp/tools/build_fonts.py /opt/aton/fonts \
 && rm -rf /tmp/tools /tmp/fonts_src /tmp/panel

COPY panel/ /opt/aton/panel/
COPY www/ /opt/aton/www/
COPY config.yaml /opt/aton/config.yaml
COPY run.sh /run.sh
RUN chmod a+x /run.sh

WORKDIR /opt/aton
CMD ["/run.sh"]

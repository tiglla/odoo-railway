FROM odoo:19.0

USER root

RUN python3 -m pip install --no-cache-dir --break-system-packages 'qifparse==0.5' \
    && python3 -c "from qifparse.parser import QifParser"

COPY addons /mnt/extra-addons
COPY entrypoint.sh /entrypoint-custom.sh

RUN chmod +x /entrypoint-custom.sh
RUN chown -R odoo:odoo /mnt/extra-addons

USER odoo

ENTRYPOINT ["/entrypoint-custom.sh"]

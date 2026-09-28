FROM odoo:19.0

USER root

COPY addons /mnt/extra-addons
COPY entrypoint.sh /entrypoint-custom.sh

RUN chmod +x /entrypoint-custom.sh
RUN chown -R odoo:odoo /mnt/extra-addons

USER odoo

ENTRYPOINT ["/entrypoint-custom.sh"]

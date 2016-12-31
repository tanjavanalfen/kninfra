{% if grains['vagrant'] %}
/home/infra/initial-db.yaml:
    file.managed:
        - source: salt://sankhara/initial-db.yaml
Initialize database:
    cmd.script:
        - source: salt://sankhara/initializeDb.py
        - onchanges:
            - file: /home/infra/initial-db.yaml
initial giedo-sync:
    cmd.run:
        - user: infra
        - creates: /home/infra/.initial-giedo-sync-run
        # - timeout: 1
        - name: >
            giedo-sync &&
            touch /home/infra/.initial-giedo-sync-run
initial scan-fotos:
    cmd.run:
        - user: infra
        - creates: /home/infra/.initial-scan-fotos-run
        - name: >
            scan-fotos &&
            touch /home/infra/.initial-scan-fotos-run
{% endif %}

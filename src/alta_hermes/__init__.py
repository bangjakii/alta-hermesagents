"""alta-hermes — jembatan antara desired state di alta-database dan runtime Hermes.

Satu arah untuk konfigurasi, satu arah untuk penyuntingan:

    repo (directives/, agents.yaml, schedules.yaml)
        --  alta-hermes sync  -->   alta-database (sumber kebenaran)
                                          |
                                    alta-hermes render
                                          v
                            ~/.hermes/profiles/<dept>/{SOUL.md, config.yaml, cron.sh}

Repo adalah tempat teksnya ditulis dan ditelaah; database adalah tempat founder
menyetelnya tanpa deploy; berkas profile adalah runtime yang dibaca Hermes.
"""

__version__ = "0.1.0"

#!/bin/sh
# Quiesced single-host backup. Run on the dedicated Linux Docker host.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
umask 077
destination=${1:?Usage: sh backup.sh /absolute/new-backup-directory}
case "$destination" in /*) ;; *) echo 'Use an absolute destination' >&2; exit 1;; esac
test ! -e "$destination" || { echo 'Backup destination already exists' >&2; exit 1; }
mkdir -p "$destination/volumes"
dc() { docker compose --env-file .env -f compose.yml "$@"; }
# Capture only running services/runtimes, so cleanup does not start disabled jobs.
dc ps --status running --services > "$destination/compose-running.txt"
sed '/^postgres$/d' "$destination/compose-running.txt" > "$destination/running-services.txt"
: > "$destination/running-runtimes.txt"
resume() {
    backup_status=$?
    trap - EXIT
    set +e
    resume_status=0
    while IFS= read -r service; do
        case "$service" in ''|edge) continue;; esac
        dc start "$service" || resume_status=1
    done < "$destination/running-services.txt"
    if grep -qx edge "$destination/running-services.txt"; then
        dc start edge || resume_status=1
    fi
    while IFS= read -r container; do
        [ -z "$container" ] || docker start "$container" >/dev/null || resume_status=1
    done < "$destination/running-runtimes.txt"
    if [ "$resume_status" -ne 0 ]; then
        echo 'Some originally running services/runtimes could not resume; inspect the saved lists.' >&2
        [ "$backup_status" -ne 0 ] || backup_status=1
    fi
    exit "$backup_status"
}
trap resume EXIT
# Close ingress and the runtime creator before taking the dynamic-container
# snapshot. Otherwise an in-flight request can restart a stopped user runtime.
for service in edge gateway; do
    if grep -qx "$service" "$destination/running-services.txt"; then
        dc stop -t 60 "$service"
    fi
done
while IFS= read -r service; do
    case "$service" in ''|edge|gateway) continue;; esac
    dc stop -t 60 "$service"
done < "$destination/running-services.txt"
docker ps -q --filter label=openclaw.platform.network=aicompany-cloud-internal > "$destination/running-runtimes.txt"
while IFS= read -r container; do [ -z "$container" ] || docker stop -t 60 "$container" >/dev/null; done < "$destination/running-runtimes.txt"
remaining_runtimes=$(docker ps -q --filter label=openclaw.platform.network=aicompany-cloud-internal)
if [ -n "$remaining_runtimes" ]; then
    echo 'User runtimes remain active; refusing an inconsistent backup.' >&2
    exit 1
fi
for database in platform enterprise_portal; do
    dc exec -T postgres sh -c 'exec pg_dump -U "$POSTGRES_USER" -Fc -d "$1"' sh "$database" > "$destination/$database.dump"
done
docker volume ls -q --filter label=com.docker.compose.project=aicompany-cloud > "$destination/compose-volumes.txt"
sed '/_postgres_data$/d' "$destination/compose-volumes.txt" > "$destination/volumes.txt"
# Per-user data volumes are created dynamically, outside Compose. Dedicated host only.
docker volume ls -q > "$destination/all-volumes.txt"
sed -n '/^openclaw-data-[a-zA-Z0-9_-]*$/p' "$destination/all-volumes.txt" >> "$destination/volumes.txt"
sort -u "$destination/volumes.txt" -o "$destination/volumes.txt"
while IFS= read -r volume; do
    [ -z "$volume" ] || docker run --rm --network none -v "$volume:/source:ro" -v "$destination/volumes:/backup" alpine:3.22 \
      sh -c 'tar -C /source -czf "/backup/$1.tar.gz" .' sh "$volume"
done < "$destination/volumes.txt"
cp .env "$destination/private.env"
dc images --format json > "$destination/images.json"
cp compose.yml Caddyfile "$destination/"
touch "$destination/BACKUP_COMPLETE"
echo 'Consistent backup complete; service resume follows. Backup contains private credentials and user files.'

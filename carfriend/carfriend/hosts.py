from django_hosts import host, patterns

host_patterns = patterns(
    "",
    host(r"www", "carfriend.urls_public", name="www"),
    host(r"api", "carfriend.urls_api", name="api"),
    host(r"master", "carfriend.urls_master", name="master"),
    host(r"teams", "carfriend.urls_teams", name="teams"),
    host(r"inspection", "carfriend.urls_inspection", name="inspection"),
    host(r"", "carfriend.urls_public", name="default"),
)

import logging, time
from modules import util
from modules.util import Failed

logger = logging.getLogger("Plex Meta Manager")

builders = ["anidb_id", "anidb_relation", "anidb_popular", "anidb_tag"]
base_url = "https://anidb.net"
urls = {
    "anime": f"{base_url}/anime",
    "popular": f"{base_url}/latest/anime/popular/?h=1",
    "relation": "/relation/graph",
    "tag": f"{base_url}/tag",
    "login": f"{base_url}/perl-bin/animedb.pl"
}

class AniDB:
    def __init__(self, config, params):
        self.config = config
        self.username = params["username"] if params else None
        self.password = params["password"] if params else None
        if params:
            if not self._login(self.username, self.password).xpath("//li[@class='sub-menu my']/@title"):
                raise Failed("AniDB Error: Login failed")

    def _request(self, url, language=None, postData=None):
        if postData:
            return self.config.post_html(url, postData, headers=util.header(language))
        else:
            return self.config.get_html(url, headers=util.header(language))

    def _login(self, username, password):
        data = {"show": "main", "xuser": username, "xpass": password, "xdoautologin": "on"}
        return self._request(urls["login"], postData=data)

    def _popular(self, language):
        response = self._request(urls["popular"], language=language)
        return util.get_int_list(response.xpath("//td[@class='name anime']/a/@href"), "AniDB ID")

    def _relations(self, anidb_id, language):
        response = self._request(f"{urls['anime']}/{anidb_id}{urls['relation']}", language=language)
        return util.get_int_list(response.xpath("//area/@href"), "AniDB ID")

    def _validate(self, anidb_id, language):
        response = self._request(f"{urls['anime']}/{anidb_id}", language=language)
        ids = response.xpath(f"//*[text()='a{anidb_id}']/text()")
        if len(ids) > 0:
            return util.regex_first_int(ids[0], "AniDB ID")
        raise Failed(f"AniDB Error: AniDB ID: {anidb_id} not found")

    def validate_anidb_list(self, anidb_list, language):
        anidb_values = []
        for anidb_id in anidb_list:
            try:
                anidb_values.append(self._validate(anidb_id, language))
            except Failed as e:
                logger.error(e)
        if len(anidb_values) > 0:
            return anidb_values
        raise Failed(f"AniDB Error: No valid AniDB IDs in {anidb_list}")

    def _tag(self, tag, limit, language):
        anidb_ids = []
        current_url = f"{urls['tag']}/{tag}"
        while True:
            response = self._request(current_url, language=language)
            anidb_ids.extend(util.get_int_list(response.xpath("//td[@class='name main anime']/a/@href"), "AniDB ID"))
            next_page_list = response.xpath("//li[@class='next']/a/@href")
            if len(anidb_ids) >= limit or len(next_page_list) == 0:
                break
            time.sleep(2)
            current_url = f"{base_url}{next_page_list[0]}"
        return anidb_ids[:limit]

    def get_items(self, method, data, language):
        pretty = util.pretty_names[method] if method in util.pretty_names else method
        anidb_ids = []
        if method == "anidb_popular":
            logger.info(f"Processing {pretty}: {data} Anime")
            anidb_ids.extend(self._popular(language)[:data])
        elif method == "anidb_tag":
            anidb_ids = self._tag(data["tag"], data["limit"], language)
            logger.info(f"Processing {pretty}: {data['limit'] if data['limit'] > 0 else 'All'} Anime from the Tag ID: {data['tag']}")
        else:
            logger.info(f"Processing {pretty}: {data}")
            if method == "anidb_id":                            anidb_ids.append(data)
            elif method == "anidb_relation":                    anidb_ids.extend(self._relations(data, language))
            else:                                               raise Failed(f"AniDB Error: Method {method} not supported")
        movie_ids, show_ids = self.config.Convert.anidb_to_ids(anidb_ids)
        logger.debug("")
        logger.debug(f"{len(anidb_ids)} AniDB IDs Found: {anidb_ids}")
        logger.debug(f"{len(movie_ids)} TMDb IDs Found: {movie_ids}")
        logger.debug(f"{len(show_ids)} TVDb IDs Found: {show_ids}")
        return movie_ids, show_ids

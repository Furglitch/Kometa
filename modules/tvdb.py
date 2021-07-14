import logging, requests, time
from modules import util
from modules.util import Failed

logger = logging.getLogger("Plex Meta Manager")

builders = [
    "tvdb_list",
    "tvdb_list_details",
    "tvdb_movie",
    "tvdb_movie_details",
    "tvdb_show",
    "tvdb_show_details"
]
base_url = "https://www.thetvdb.com"
alt_url = "https://thetvdb.com"
urls = {
    "list": f"{base_url}/lists/",
    "alt_list": f"{alt_url}/lists/",
    "series": f"{base_url}/series/",
    "alt_series": f"{alt_url}/series/",
    "movies": f"{base_url}/movies/",
    "alt_movies": f"{alt_url}/movies/",
    "series_id": f"{base_url}/dereferrer/series/",
    "movie_id": f"{base_url}/dereferrer/movie/"
}

class TVDbObj:
    def __init__(self, tvdb_url, language, is_movie, config):
        self.tvdb_url = tvdb_url.strip()
        self.language = language
        self.is_movie = is_movie
        self.config = config
        if not self.is_movie and self.tvdb_url.startswith((urls["series"], urls["alt_series"], urls["series_id"])):
            self.media_type = "Series"
        elif self.is_movie and self.tvdb_url.startswith((urls["movies"], urls["alt_movies"], urls["movie_id"])):
            self.media_type = "Movie"
        else:
            raise Failed(f"TVDb Error: {self.tvdb_url} must begin with {urls['movies'] if self.is_movie else urls['series']}")

        response = self.config.get_html(self.tvdb_url, headers=util.header(self.language))
        results = response.xpath(f"//*[text()='TheTVDB.com {self.media_type} ID']/parent::node()/span/text()")
        if len(results) > 0:
            self.id = int(results[0])
        elif self.tvdb_url.startswith(urls["movie_id"]):
            raise Failed(f"TVDb Error: Could not find a TVDb Movie using TVDb Movie ID: {self.tvdb_url[len(urls['movie_id']):]}")
        elif self.tvdb_url.startswith(urls["series_id"]):
            raise Failed(f"TVDb Error: Could not find a TVDb Series using TVDb Series ID: {self.tvdb_url[len(urls['series_id']):]}")
        else:
            raise Failed(f"TVDb Error: Could not find a TVDb {self.media_type} ID at the URL {self.tvdb_url}")

        results = response.xpath("//div[@class='change_translation_text' and @data-language='eng']/@data-title")
        if len(results) > 0 and len(results[0]) > 0:
            self.title = results[0]
        else:
            raise Failed(f"TVDb Error: Name not found from TVDb URL: {self.tvdb_url}")

        results = response.xpath("//div[@class='row hidden-xs hidden-sm']/div/img/@src")
        self.poster_path = results[0] if len(results) > 0 and len(results[0]) > 0 else None

        results = response.xpath("(//h2[@class='mt-4' and text()='Backgrounds']/following::div/a/@href)[1]")
        self.background_path = results[0] if len(results) > 0 and len(results[0]) > 0 else None

        results = response.xpath("//div[@class='block']/div[not(@style='display:none')]/p/text()")
        self.summary = results[0] if len(results) > 0 and len(results[0]) > 0 else None

        tmdb_id = None
        if self.is_movie:
            results = response.xpath("//*[text()='TheMovieDB.com']/@href")
            if len(results) > 0:
                try:
                    tmdb_id = util.regex_first_int(results[0], "TMDb ID")
                except Failed:
                    pass
            if tmdb_id is None:
                results = response.xpath("//*[text()='IMDB']/@href")
                if len(results) > 0:
                    try:
                        tmdb_id = self.config.Convert.imdb_to_tmdb(util.get_id_from_imdb_url(results[0]), fail=True)
                    except Failed:
                        pass
            if tmdb_id is None:
                raise Failed(f"TVDB Error: No TMDb ID found for {self.title}")
        self.tmdb_id = tmdb_id

class TVDb:
    def __init__(self, config):
        self.config = config

    def get_movie_or_series(self, language, tvdb_url, is_movie):
        return self.get_movie(language, tvdb_url) if is_movie else self.get_series(language, tvdb_url)

    def get_series(self, language, tvdb_url):
        try:
            tvdb_url = f"{urls['series_id']}{int(tvdb_url)}"
        except ValueError:
            pass
        return TVDbObj(tvdb_url, language, False, self.config)

    def get_movie(self, language, tvdb_url):
        try:
            tvdb_url = f"{urls['movie_id']}{int(tvdb_url)}"
        except ValueError:
            pass
        return TVDbObj(tvdb_url, language, True, self.config)

    def get_list_description(self, tvdb_url, language):
        response = self.config.get_html(tvdb_url, headers=util.header(language))
        description = response.xpath("//div[@class='block']/div[not(@style='display:none')]/p/text()")
        return description[0] if len(description) > 0 and len(description[0]) > 0 else ""

    def _ids_from_url(self, tvdb_url, language):
        show_ids = []
        movie_ids = []
        tvdb_url = tvdb_url.strip()
        if tvdb_url.startswith((urls["list"], urls["alt_list"])):
            try:
                response = self.config.get_html(tvdb_url, headers=util.header(language))
                items = response.xpath("//div[@class='col-xs-12 col-sm-12 col-md-8 col-lg-8 col-md-pull-4']/div[@class='row']")
                for item in items:
                    title = item.xpath(".//div[@class='col-xs-12 col-sm-9 mt-2']//a/text()")[0]
                    item_url = item.xpath(".//div[@class='col-xs-12 col-sm-9 mt-2']//a/@href")[0]
                    if item_url.startswith("/series/"):
                        try:
                            show_ids.append(self.get_series(language, f"{base_url}{item_url}").id)
                        except Failed as e:
                            logger.error(f"{e} for series {title}")
                    elif item_url.startswith("/movies/"):
                        try:
                            tmdb_id = self.get_movie(language, f"{base_url}{item_url}").tmdb_id
                            if tmdb_id:
                                movie_ids.append(tmdb_id)
                            else:
                                raise Failed(f"TVDb Error: TMDb ID not found from TVDb URL: {tvdb_url}")
                        except Failed as e:
                            logger.error(f"{e} for series {title}")
                    else:
                        logger.error(f"TVDb Error: Skipping Movie: {title}")
                    time.sleep(2)
                if len(show_ids) > 0 or len(movie_ids) > 0:
                    return movie_ids, show_ids
                raise Failed(f"TVDb Error: No TVDb IDs found at {tvdb_url}")
            except requests.exceptions.MissingSchema:
                util.print_stacktrace()
                raise Failed(f"TVDb Error: URL Lookup Failed for {tvdb_url}")
        else:
            raise Failed(f"TVDb Error: {tvdb_url} must begin with {urls['list']}")

    def get_items(self, method, data, language):
        pretty = util.pretty_names[method] if method in util.pretty_names else method
        show_ids = []
        movie_ids = []
        logger.info(f"Processing {pretty}: {data}")
        if method == "tvdb_show":
            show_ids.append(self.get_series(language, data).id)
        elif method == "tvdb_movie":
            movie_ids.append(self.get_movie(language, data).tmdb_id)
        elif method == "tvdb_list":
            tmdb_ids, tvdb_ids = self._ids_from_url(data, language)
            movie_ids.extend(tmdb_ids)
            show_ids.extend(tvdb_ids)
        else:
            raise Failed(f"TVDb Error: Method {method} not supported")
        logger.debug("")
        logger.debug(f"{len(movie_ids)} TMDb IDs Found: {movie_ids}")
        logger.debug(f"{len(show_ids)} TVDb IDs Found: {show_ids}")
        return movie_ids, show_ids

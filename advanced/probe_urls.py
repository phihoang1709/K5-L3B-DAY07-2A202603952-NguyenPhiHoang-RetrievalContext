"""One-off probe of candidate Vietcombank VN annual-report 2024 PDF URLs.

URLs are full literal constants (host pinned to vietcombank.com.vn, https only).
"""
import urllib.request

ALLOWED_HOST = 'vietcombank.com.vn'
PATH = ('/-/media/Project/VCB-Sites/VCB/Nha-Dau-tu/Files/BC-dinh-ky/'
        'BC-thuong-nien/2024/')
CANDIDATES = [
    'VN_VCB-Annual-Report-2024_Full_250426_FN_compressed.pdf',
    'VN_VCB-Annual-Report-2024_Full_250426_FN.pdf',
    'VN_VCB-Bao-cao-thuong-nien-2024_Full_250426_FN_compressed.pdf',
    'VN_Bao-cao-thuong-nien-2024_Full_250426_FN_compressed.pdf',
    'VN_VCB-Annual-Report-2024_Full.pdf',
    'VN_VCB-Annual-Report-2024_compressed.pdf',
    'EN_VCB-Annual-Report-2024_Full_250426_FN_compressed.pdf',
]


def guarded(name: str) -> str:
    """Build the full URL from pinned host + constant path + file name."""
    url = f'https://{ALLOWED_HOST}{PATH}{name}'
    host = urllib.parse.urlsplit(url).hostname
    if urllib.parse.urlsplit(url).scheme != 'https' or host != ALLOWED_HOST:
        raise ValueError('URL outside the allowlisted host')
    return url


def main():
    for name in CANDIDATES:
        request = urllib.request.Request(guarded(name), method='HEAD')
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                print(response.status, response.headers.get('Content-Length'), name)
        except Exception as exc:  # noqa: BLE001 - probe only
            print('ERR', getattr(exc, 'code', str(exc)[:60]), name)


if __name__ == '__main__':
    main()

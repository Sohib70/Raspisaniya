"""
`views.py` (5573 qator) shu `views/` paketiga bo'lib chiqarilgan.
Bu fayl HAMMA modullarni qayta eksport qiladi — `urls.py`dagi
`from . import views` va `views.build_schedule` kabi chaqiruvlar
ILGARIGIDEK ishlayveradi.
"""
from ._shared import *          # noqa: F401,F403
from .schedule import *          # noqa: F401,F403
from .lessons import *            # noqa: F401,F403
from .teachers import *            # noqa: F401,F403
from .students import *             # noqa: F401,F403
from .rooms_subjects import *        # noqa: F401,F403
from .exports import *                # noqa: F401,F403
from .admin_tools import *             # noqa: F401,F403

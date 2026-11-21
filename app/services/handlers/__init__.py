from .generic_json import GenericJsonHandler
from .subscription import SubscriptionHandler

HANDLER_MAP = {
    "generic_json": GenericJsonHandler,
    "subscription": SubscriptionHandler,
}

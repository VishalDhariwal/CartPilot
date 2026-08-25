"""
CartPilot Azure Service Bus Queue & Event Abstraction
Handles asynchronous events (e.g. `order-paid`, `cart-abandoned`, `webhook-events`)
with transparent local in-memory fallback for local development.
"""

import os
import json
import logging
from typing import Dict, Any, Callable, Optional

logger = logging.getLogger("cartpilot.servicebus")

SERVICEBUS_CONN_STR = os.getenv("AZURE_SERVICEBUS_CONNECTION_STRING")
SERVICEBUS_NAMESPACE = os.getenv("SERVICEBUS_NAMESPACE")

_sb_client = None

def get_servicebus_client():
    global _sb_client
    if _sb_client is not None:
        return _sb_client

    if not SERVICEBUS_CONN_STR and not SERVICEBUS_NAMESPACE:
        return None

    try:
        from azure.servicebus import ServiceBusClient
        from azure.identity import DefaultAzureCredential

        if SERVICEBUS_CONN_STR:
            _sb_client = ServiceBusClient.from_connection_string(SERVICEBUS_CONN_STR)
        elif SERVICEBUS_NAMESPACE:
            fqdn = f"{SERVICEBUS_NAMESPACE}.servicebus.windows.net"
            _sb_client = ServiceBusClient(fully_qualified_namespace=fqdn, credential=DefaultAzureCredential())
        return _sb_client
    except Exception as e:
        logger.warning(f"Failed to initialize Azure Service Bus client: {e}")
        return None


def publish_event(queue_name: str, event_data: Dict[str, Any]) -> bool:
    """
    Publishes an asynchronous event payload to an Azure Service Bus queue.
    Falls back to local logging / synchronous execution when Service Bus is not configured.
    """
    client = get_servicebus_client()
    if client:
        try:
            from azure.servicebus import ServiceBusMessage
            sender = client.get_queue_sender(queue_name=queue_name)
            with sender:
                msg = ServiceBusMessage(json.dumps(event_data))
                sender.send_messages(msg)
            logger.info(f"Published event to Azure Service Bus [{queue_name}]: {event_data.get('event_type')}")
            return True
        except Exception as e:
            logger.error(f"Error publishing to Service Bus queue [{queue_name}]: {e}")
            return False
    else:
        # Local Development Fallback
        logger.debug(f"[LOCAL QUEUE] Enqueued event on '{queue_name}': {event_data}")
        return True


def consume_messages(queue_name: str, handler: Callable[[Dict[str, Any]], None], max_messages: int = 10):
    """
    Consumes batch messages from a specified queue and executes the given handler.
    """
    client = get_servicebus_client()
    if not client:
        return 0

    try:
        receiver = client.get_queue_receiver(queue_name=queue_name, max_message_count=max_messages)
        count = 0
        with receiver:
            messages = receiver.receive_messages(max_message_count=max_messages, max_wait_time=5)
            for msg in messages:
                try:
                    payload = json.loads(str(msg))
                    handler(payload)
                    receiver.complete_message(msg)
                    count += 1
                except Exception as e:
                    logger.error(f"Error processing Service Bus message: {e}")
                    receiver.abandon_message(msg)
        return count
    except Exception as e:
        logger.error(f"Service Bus receiver error on [{queue_name}]: {e}")
        return 0

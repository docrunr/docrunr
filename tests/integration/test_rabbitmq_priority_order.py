"""RabbitMQ native priority ordering on ``docrunr.jobs`` (live broker).

Uses ``basic_qos(prefetch_count=1)`` and defers ack on the first delivery so additional
messages stay **ready** in the queue; a higher-priority message published while the consumer
is blocked must be delivered next.
"""

from __future__ import annotations

import json
import threading
import time
import uuid

import pika
import pytest
from docrunr_worker.job_messages import EXTRACTION_JOB_QUEUE_ARGUMENTS

from tests.integration.rmq_helpers import rabbitmq_params, try_connect_rabbitmq

pytestmark = pytest.mark.integration


def _require_rabbitmq() -> None:
    if not try_connect_rabbitmq():
        pytest.skip(
            "RabbitMQ not reachable (start with: docker compose up -d rabbitmq)",
        )


def test_higher_priority_delivered_before_lower_when_queued_behind_prefetch() -> None:
    _require_rabbitmq()
    queue = f"docrunr.jobs.priority-test.{uuid.uuid4().hex}"

    params = rabbitmq_params()
    recv_conn = pika.BlockingConnection(params)
    recv_ch = recv_conn.channel()
    recv_ch.queue_declare(queue=queue, durable=True, arguments=EXTRACTION_JOB_QUEUE_ARGUMENTS)
    recv_ch.queue_purge(queue)

    pub_conn = pika.BlockingConnection(params)
    pub_ch = pub_conn.channel()
    pub_ch.queue_declare(queue=queue, durable=True, arguments=EXTRACTION_JOB_QUEUE_ARGUMENTS)

    order: list[str] = []
    hold = threading.Event()
    release = threading.Event()
    done = threading.Event()

    def on_message(
        ch: pika.adapters.blocking_connection.BlockingChannel,
        method: pika.spec.Basic.Deliver,
        _props: pika.spec.BasicProperties,
        body: bytes,
    ) -> None:
        data = json.loads(body.decode())
        order.append(str(data.get("label", "")))
        if data.get("label") == "first":
            hold.set()
            release.wait(timeout=30.0)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        if len(order) >= 3:
            ch.stop_consuming()
            done.set()

    recv_ch.basic_qos(prefetch_count=1)
    recv_ch.basic_consume(queue=queue, on_message_callback=on_message, auto_ack=False)
    t = threading.Thread(target=recv_ch.start_consuming, daemon=True)
    t.start()

    low_body = json.dumps({"label": "low", "job_id": str(uuid.uuid4())}).encode()
    high_body = json.dumps({"label": "high", "job_id": str(uuid.uuid4())}).encode()
    first_body = json.dumps({"label": "first", "job_id": str(uuid.uuid4())}).encode()

    pub_ch.basic_publish(
        exchange="",
        routing_key=queue,
        body=first_body,
        properties=pika.BasicProperties(delivery_mode=2, priority=0),
    )
    assert hold.wait(timeout=10.0), "consumer did not receive first message"

    pub_ch.basic_publish(
        exchange="",
        routing_key=queue,
        body=low_body,
        properties=pika.BasicProperties(delivery_mode=2, priority=0),
    )
    pub_ch.basic_publish(
        exchange="",
        routing_key=queue,
        body=high_body,
        properties=pika.BasicProperties(delivery_mode=2, priority=10),
    )
    time.sleep(0.3)
    release.set()

    assert done.wait(timeout=30.0)
    t.join(timeout=5.0)

    assert order == ["first", "high", "low"]

    pub_ch.close()
    pub_conn.close()
    recv_ch.queue_delete(queue=queue)
    recv_ch.close()
    recv_conn.close()

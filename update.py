import csv
import json
import os
import re
import sys
import time
from typing import Any

from dotenv import load_dotenv
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import (
    BatchCreateRecordSetsTaskItem,
    BatchCreateRecordSetsTaskRequest,
    BatchCreateRecordSetsTaskRequestBody,
    BatchDeleteRecordSetWithLineRequest,
    BatchDeleteRecordSetWithLineRequestBody,
    DeleteBatchCreateRecordSetsTaskRequest,
    DnsClient,
    ListPublicZonesRequest,
    ShowRecordSetByZoneRequest,
)


DEFAULT_ENDPOINT = "https://dns.cn-east-3.myhuaweicloud.com"
CSV_FILE = "ips.csv"

load_dotenv()


def normalize_domain(value: str | None) -> str:
    if not value:
        return ""
    return value if value.endswith(".") else f"{value}."


def safe_float(value: str) -> float:
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        return float(match.group(0)) if match else 0.0


def get_error_code(exc: Exception) -> str | None:
    error_code = getattr(exc, "error_code", None)
    if error_code:
        return str(error_code)

    data = getattr(exc, "data", None)
    if isinstance(data, dict) and data.get("code"):
        return str(data["code"])

    return None


def get_error_message(exc: Exception) -> str:
    error_msg = getattr(exc, "error_msg", None)
    if error_msg:
        return str(error_msg)

    message = getattr(exc, "message", None)
    if message:
        return str(message)

    data = getattr(exc, "data", None)
    if isinstance(data, dict):
        if data.get("message"):
            return str(data["message"])
        return json.dumps(data, ensure_ascii=False)

    return str(exc)


def stringify_response(response: Any) -> str:
    if hasattr(response, "to_str"):
        return response.to_str()
    return json.dumps(response, ensure_ascii=False, default=str)


def load_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    with open(CSV_FILE, "r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)

        for columns in reader:
            if len(columns) < 9:
                continue

            _, isp, ip, loss, _latency, _speed, bw, _colo, _time = columns[:9]
            rows.append({"isp": isp, "ip": ip, "loss": loss, "bw": bw})

    return rows


def build_target(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    filtered = [
        row for row in rows if row["loss"] == "0.00%" and safe_float(row["bw"]) > 100
    ]
    return {
        "bgp": [row for row in filtered if row["isp"] == "多线"],
        "cmcc": [row for row in filtered if row["isp"] == "移动"],
        "ctcc": [row for row in filtered if row["isp"] == "电信"],
        "cucc": [row for row in filtered if row["isp"] == "联通"],
        "ipv6": [row for row in filtered if row["isp"] == "IPV6"],
    }


def build_client(ak: str, sk: str, endpoint: str) -> DnsClient:
    credentials = BasicCredentials(ak, sk)
    return DnsClient.new_builder().with_credentials(credentials).with_endpoint(
        endpoint
    ).build()


def append_record_set(
    recordsets: list[BatchCreateRecordSetsTaskItem],
    *,
    record_type: str,
    records: list[str],
    line: str | None = None,
) -> None:
    if not records:
        return

    item = BatchCreateRecordSetsTaskItem(
        type=record_type,
        weight=1,
        records=records,
    )
    if line:
        item.line = line

    recordsets.append(item)


def clear_batch_create_task(client: DnsClient, zone_id: str) -> None:
    request = DeleteBatchCreateRecordSetsTaskRequest(zone_id=zone_id)

    try:
        client.delete_batch_create_record_sets_task(request)
        print("ℹ️ 已清理旧的批量创建任务")
    except Exception as exc:
        print(f"ℹ️ 清理旧的批量创建任务时跳过：{get_error_message(exc)}")


def create_record_sets_task_with_retry(
    client: DnsClient,
    zone_id: str,
    request: BatchCreateRecordSetsTaskRequest,
    max_attempts: int = 6,
) -> Any:
    for attempt in range(1, max_attempts + 1):
        try:
            return client.batch_create_record_sets_task(request)
        except Exception as exc:
            if get_error_code(exc) != "DNS.0019" or attempt == max_attempts:
                raise

            wait_seconds = attempt * 5
            print(
                f"⚠️ 检测到批量导入任务仍存在，{wait_seconds} 秒后重试 "
                f"({attempt}/{max_attempts})"
            )
            time.sleep(wait_seconds)
            clear_batch_create_task(client, zone_id)

    raise RuntimeError("创建记录任务重试结束，但未获得响应")


def main() -> None:
    ak = os.getenv("CLOUD_SDK_AK")
    sk = os.getenv("CLOUD_SDK_SK")
    domain = normalize_domain(os.getenv("DOMAIN"))

    if not ak or not sk or not domain:
        print("❌ 请设置 CLOUD_SDK_AK, CLOUD_SDK_SK, DOMAIN 环境变量")
        sys.exit(1)

    endpoint = os.getenv("CLOUD_SDK_ENDPOINT", DEFAULT_ENDPOINT)
    fallback_domain = os.getenv("FALLBACK_DOMAIN", "saas.sin.fan")

    target = build_target(load_rows())
    client = build_client(ak, sk, endpoint)

    domain_id: str | None = None
    try:
        result = client.list_public_zones(ListPublicZonesRequest())
        for zone in result.zones or []:
            if getattr(zone, "name", None) == domain and not domain_id:
                domain_id = getattr(zone, "id", None)
    except Exception as exc:
        print(f"❌ 查询域名ID失败: {get_error_message(exc)}")
        sys.exit(1)

    if not domain_id:
        print("❌ 未找到匹配的域名")
        sys.exit(1)

    recordset_ids: list[str] = []
    try:
        result = client.show_record_set_by_zone(
            ShowRecordSetByZoneRequest(zone_id=domain_id)
        )
        for recordset in result.recordsets or []:
            recordset_id = getattr(recordset, "id", None)
            recordset_type = getattr(recordset, "type", None)
            if recordset_id and recordset_type in {"A", "AAAA", "CNAME"}:
                recordset_ids.append(recordset_id)
    except Exception as exc:
        print(f"❌ 列出相关记录失败: {get_error_message(exc)}")
        sys.exit(1)

    if recordset_ids:
        request = BatchDeleteRecordSetWithLineRequest(
            zone_id=domain_id,
            body=BatchDeleteRecordSetWithLineRequestBody(recordset_ids=recordset_ids),
        )
        try:
            client.batch_delete_record_set_with_line(request)
            print("✅ 删除旧记录成功")
        except Exception as exc:
            print(f"❌ 删除旧记录失败: {get_error_message(exc)}")
            sys.exit(1)

    recordsets: list[BatchCreateRecordSetsTaskItem] = []

    append_record_set(
        recordsets,
        record_type="A",
        line="CN",
        records=[row["ip"] for row in target["bgp"]],
    )
    append_record_set(
        recordsets,
        record_type="A",
        line="Yidong",
        records=[row["ip"] for row in target["cmcc"]],
    )
    append_record_set(
        recordsets,
        record_type="A",
        line="Dianxin",
        records=[row["ip"] for row in target["ctcc"]],
    )
    append_record_set(
        recordsets,
        record_type="A",
        line="Liantong",
        records=[row["ip"] for row in target["cucc"]],
    )
    # IPV6
    # append_record_set(
    #     recordsets,
    #     record_type="AAAA",
    #     records=[row["ip"] for row in target["ipv6"]],
    # )
    # fallback
    append_record_set(
        recordsets,
        record_type="CNAME",
        records=[fallback_domain],
    )

    if not recordsets:
        print("❌ 没有可创建的记录")
        sys.exit(1)

    request = BatchCreateRecordSetsTaskRequest(
        zone_id=domain_id,
        body=BatchCreateRecordSetsTaskRequestBody(recordsets=recordsets),
    )

    try:
        clear_batch_create_task(client, domain_id)
        result = create_record_sets_task_with_retry(client, domain_id, request)
        print(f"✅ 创建新记录成功: {stringify_response(result)}")
    except Exception as exc:
        print(f"❌ 创建新记录失败: {get_error_message(exc)}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"❌ 执行失败: {get_error_message(exc)}")
        sys.exit(1)

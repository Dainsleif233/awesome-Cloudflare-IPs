import { readFileSync } from 'fs';
import * as core from '@huaweicloud/huaweicloud-sdk-core';
import * as dns from "@huaweicloud/huaweicloud-sdk-dns/v2/public-api";
import * as dotenv from 'dotenv';

// 加载 .env 文件中的环境变量
dotenv.config();

const lines = readFileSync('ips.csv', 'utf-8').trim().split('\n');
// 跳过表头
const rows = lines.slice(1).map(line => {
    const [_idx, isp, ip, loss, _latency, _speed, bw, _colo, _time] = line.split(',');
    return { isp, ip, loss, bw };
});
const filtered = rows.filter(r => r.loss === '0.00%' && parseFloat(r.bw) > 100);
const target = {
    bgp: filtered.filter(r => r.isp === '多线'),
    cmcc: filtered.filter(r => r.isp === '移动'),
    ctcc: filtered.filter(r => r.isp === '电信'),
    cucc: filtered.filter(r => r.isp === '联通'),
    ipv6: filtered.filter(r => r.isp === 'IPV6')
};

// 初始化华为云DNS客户端
const ak = process.env.CLOUD_SDK_AK;
const sk = process.env.CLOUD_SDK_SK;
const domain = process.env.DOMAIN ? process.env.DOMAIN.endsWith('.') ? process.env.DOMAIN : process.env.DOMAIN + '.' : '';
if (!ak || !sk || domain === '') {
    console.error("❌ 请设置 CLOUD_SDK_AK, CLOUD_SDK_SK, DOMAIN 环境变量");
    process.exit(1);
}
const endpoint = process.env.CLOUD_SDK_ENDPOINT || "https://dns.cn-east-3.myhuaweicloud.com";
const credentials = new core.BasicCredentials().withAk(ak).withSk(sk);
const client = dns.DnsClient.newBuilder().withCredential(credentials).withEndpoint(endpoint).build();

function sleep(ms: number) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function getErrorCode(ex: unknown) {
    return (ex as { data?: { code?: string } })?.data?.code;
}

function getErrorMessage(ex: unknown) {
    return (ex as { data?: { message?: string }; message?: string })?.data?.message
        || (ex as { message?: string })?.message
        || JSON.stringify(ex);
}

function appendRecordSet(
    list: dns.BatchCreateRecordSetsTaskItem[],
    options: { type: string; records: string[]; line?: string }
) {
    if (options.records.length === 0) return;

    let item = new dns.BatchCreateRecordSetsTaskItem()
        .withWeight(1)
        .withType(options.type)
        .withRecords(options.records);

    if (options.line) {
        item = item.withLine(options.line);
    }

    list.push(item);
}

async function clearBatchCreateTask(zoneId: string) {
    const request = new dns.DeleteBatchCreateRecordSetsTaskRequest();
    request.zoneId = zoneId;

    try {
        await client.deleteBatchCreateRecordSetsTask(request);
        console.log("ℹ️ 已清理旧的批量创建任务");
    } catch (ex) {
        console.log(`ℹ️ 清理旧的批量创建任务时跳过：${getErrorMessage(ex)}`);
    }
}

async function createRecordSetsTaskWithRetry(
    zoneId: string,
    request: dns.BatchCreateRecordSetsTaskRequest,
    maxAttempts = 6
) {
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            return await client.batchCreateRecordSetsTask(request);
        } catch (ex) {
            if (getErrorCode(ex) !== "DNS.0019" || attempt === maxAttempts) {
                throw ex;
            }

            const waitSeconds = attempt * 5;
            console.log(`⚠️ 检测到批量导入任务仍存在，${waitSeconds} 秒后重试 (${attempt}/${maxAttempts})`);
            await sleep(waitSeconds * 1000);
            await clearBatchCreateTask(zoneId);
        }
    }
}

async function main() {
    // 查询域名ID
    let domainId: string | undefined;
    let request: any = new dns.ListPublicZonesRequest();

    try {
        const result = await client.listPublicZones(request);
        result.zones?.forEach(zone => {
            if (zone.name === domain && !domainId) domainId = zone.id;
        });
    } catch (ex) {
        console.error("❌ 查询域名ID失败:" + JSON.stringify(ex));
        process.exit(1);
    }

    if (!domainId) {
        console.error("❌ 未找到匹配的域名");
        process.exit(1);
    }

    // 列出所有相关记录
    const sets: string[] = [];
    request = new dns.ShowRecordSetByZoneRequest();
    request.zoneId = domainId;

    try {
        const result = await client.showRecordSetByZone(request);
        result.recordsets?.forEach(set => {
            if (set.id && (set.type === 'A' || set.type === 'AAAA' || set.type === 'CNAME')) sets.push(set.id);
        });
    } catch (ex) {
        console.error("❌ 列出相关记录失败:" + JSON.stringify(ex));
        process.exit(1);
    }

    // 删除旧记录
    if (sets.length > 0) {
        request = new dns.BatchDeleteRecordSetWithLineRequest();
        request.zoneId = domainId;
        let body: any = new dns.BatchDeleteRecordSetWithLineRequestBody();
        body.withRecordsetIds(sets);
        request.withBody(body);

        try {
            const result = await client.batchDeleteRecordSetWithLine(request);
            console.log("✅ 删除旧记录成功");
        } catch (ex) {
            console.error("❌ 删除旧记录失败:" + JSON.stringify(ex));
            process.exit(1);
        }
    }

    // 创建新记录
    request = new dns.BatchCreateRecordSetsTaskRequest();
    request.zoneId = domainId;
    const body: any = new dns.BatchCreateRecordSetsTaskRequestBody();
    const listbodyRecordsets: dns.BatchCreateRecordSetsTaskItem[] = [];

    // BGP
    appendRecordSet(listbodyRecordsets, {
        type: "A",
        line: "CN",
        records: target.bgp.map(r => r.ip)
    });
    // CMCC
    appendRecordSet(listbodyRecordsets, {
        type: "A",
        line: "Yidong",
        records: target.cmcc.map(r => r.ip)
    });
    // CTCC
    appendRecordSet(listbodyRecordsets, {
        type: "A",
        line: "Dianxin",
        records: target.ctcc.map(r => r.ip)
    });
    // CUCC
    appendRecordSet(listbodyRecordsets, {
        type: "A",
        line: "Liantong",
        records: target.cucc.map(r => r.ip)
    });
    // IPV6
    // appendRecordSet(listbodyRecordsets, {
    //     type: "AAAA",
    //     records: target.ipv6.map(r => r.ip)
    // });
    // fallback
    appendRecordSet(listbodyRecordsets, {
        type: "CNAME",
        records: [process.env.FALLBACK_DOMAIN || "saas.sin.fan"]
    });

    if (listbodyRecordsets.length === 0) {
        console.error("❌ 没有可创建的记录");
        process.exit(1);
    }

    body.withRecordsets(listbodyRecordsets);
    request.withBody(body);

    try {
        await clearBatchCreateTask(domainId);
        const result = await createRecordSetsTaskWithRetry(domainId, request);
        console.log("✅ 创建新记录成功:" + JSON.stringify(result));
    } catch (ex) {
        console.error("❌ 创建新记录失败:" + JSON.stringify(ex));
        process.exit(1);
    }
}

main().catch(ex => {
    console.error("❌ 执行失败:" + JSON.stringify(ex));
    process.exit(1);
});

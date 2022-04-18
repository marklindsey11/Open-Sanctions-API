import json
import logging
from aiohttp import ClientSession, ClientTimeout
from aiocsv import AsyncDictReader
from typing import AsyncGenerator, Dict
from asyncstdlib.functools import cache

from yente import settings
from yente.data.entity import Entity
from yente.data.dataset import Dataset, Datasets
from yente.data.statements import StatementModel
from yente.util import AsyncTextReaderWrapper

log = logging.getLogger(__name__)
http_timeout = ClientTimeout(
    total=3600 * 6,
    connect=None,
    sock_read=None,
    sock_connect=None,
)


@cache
async def get_data_index():
    async with ClientSession(timeout=http_timeout) as client:
        async with client.get(settings.DATA_INDEX) as resp:
            return await resp.json()


@cache
async def get_datasets() -> Datasets:
    index = await get_data_index()
    datasets: Datasets = {}
    for item in index.get("datasets", []):
        dataset = Dataset(item)
        datasets[dataset.name] = dataset
    return datasets


async def get_scope() -> Dataset:
    datasets = await get_datasets()
    dataset = datasets.get(settings.SCOPE_DATASET)
    if dataset is None:
        raise RuntimeError("Scope dataset does not exist: %s" % settings.SCOPE_DATASET)
    return dataset


async def check_update():
    get_data_index.cache_clear()
    get_datasets.cache_clear()


async def get_dataset_entities(dataset: Dataset) -> AsyncGenerator[Entity, None]:
    if dataset.entities_url is None:
        raise ValueError("Dataset has no entity source: %s" % dataset)
    datasets = await get_datasets()
    async with ClientSession(timeout=http_timeout, read_bufsize=2**17) as client:
        async with client.get(dataset.entities_url) as resp:
            async for line in resp.content:
                data = json.loads(line)
                entity = Entity.from_os_data(data, datasets)
                if not len(entity.datasets):
                    entity.datasets.add(dataset)
                yield entity


async def get_statements() -> AsyncGenerator[StatementModel, None]:
    index = await get_data_index()
    url = index.get("statements_url")
    if url is None:
        raise ValueError("No statement URL in index")
    async with ClientSession(timeout=http_timeout, read_bufsize=2**17) as client:
        async with client.get(url) as resp:
            wrapper = AsyncTextReaderWrapper(resp.content, "utf-8")
            async for row in AsyncDictReader(wrapper):
                yield StatementModel.from_row(row)
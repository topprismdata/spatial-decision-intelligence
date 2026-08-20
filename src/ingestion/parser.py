"""
Data Ingestion Parser - Converts external tables to immutable SourceRecord objects.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from src.domain.models import SourceRecord


class ExcelIngestionParser:
    """Parser for residential/venue excel tables."""

    @staticmethod
    def parse_file(file_path: str, sheet_name: str = "sheet1", batch_id: str = "BATCH_20260818") -> List[SourceRecord]:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        records: List[SourceRecord] = []

        for idx, row in df.iterrows():
            rec_id = f"SRC_{idx+1:06d}"
            biz_id = str(row.get("小区编码", "")) if pd.notnull(row.get("小区编码")) else None
            name = str(row.get("小区名称", "")).strip() if pd.notnull(row.get("小区名称")) else ""
            address = str(row.get("小区地址", "")).strip() if pd.notnull(row.get("小区地址")) else ""
            province = str(row.get("省份名称", "") or row.get("省[内置]", "")).strip()
            city = str(row.get("城市", "") or row.get("市[内置]", "")).strip()
            district = str(row.get("区[内置]", "")).strip() if pd.notnull(row.get("区[内置]")) else ""
            street = str(row.get("街道[内置]", "")).strip() if pd.notnull(row.get("街道[内置]")) else ""

            # Point coordinates
            lng = float(row["经度"]) if pd.notnull(row.get("经度")) else None
            lat = float(row["纬度"]) if pd.notnull(row.get("纬度")) else None

            # Polygon
            poly_wkt = str(row.get("坐标面[内置]", "")).strip() if pd.notnull(row.get("坐标面[内置]")) else None
            if poly_wkt == "" or poly_wkt == "nan" or poly_wkt == "None":
                poly_wkt = None

            area = float(row["面积[内置]"]) if pd.notnull(row.get("面积[内置]")) else None

            # Extra raw attributes
            attrs: Dict[str, Any] = {}
            for col in df.columns:
                if col not in ["小区编码", "小区名称", "小区地址", "省份名称", "省[内置]", "城市", "市[内置]", "区[内置]", "街道[内置]", "经度", "纬度", "坐标面[内置]", "面积[内置]"]:
                    val = row.get(col)
                    if pd.notnull(val):
                        attrs[col] = val

            rec = SourceRecord(
                source_record_id=rec_id,
                source_system="excel_import",
                source_batch_id=batch_id,
                source_business_id=biz_id,
                name_raw=name,
                address_raw=address,
                province_raw=province,
                city_raw=city,
                district_raw=district,
                street_raw=street,
                point_raw_lng=lng,
                point_raw_lat=lat,
                geometry_raw_wkt=poly_wkt,
                area_raw=area,
                attributes_raw=attrs
            )
            records.append(rec)

        return records

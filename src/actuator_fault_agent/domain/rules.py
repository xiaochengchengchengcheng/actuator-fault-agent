from collections.abc import Iterable

from .models import MeasurementSnapshot, RiskLevel, RuleFinding


def _number(values: dict, key: str) -> float | None:
    value = values.get(key)
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _failed(values: dict, key: str) -> bool:
    value = values.get(key)
    if isinstance(value, bool):
        return not value
    if isinstance(value, str):
        return value.strip().lower() in {"fail", "failed", "ng", "false", "0"}
    return False


def screen_measurements(snapshot: MeasurementSnapshot) -> list[RuleFinding]:
    """Conservative demo rules. Replace thresholds with approved model/station limits."""
    values = snapshot.values
    findings: list[RuleFinding] = []

    if _failed(values, "insulation_test_pass") or _failed(values, "hipot_test_pass"):
        findings.append(
            RuleFinding(
                code="ELECTRICAL_SAFETY_FAIL",
                title="电气安全测试失败",
                risk=RiskLevel.CRITICAL,
                observation="绝缘或耐压测试结果为失败。",
                possible_causes=["绕组绝缘损伤", "引线压伤或接线错误", "污染或受潮"],
                verification_steps=[
                    "保持隔离并禁止再次通电",
                    "复核测试程序、夹具与接地连接",
                    "按受控工艺检查绕组、引线和连接器",
                ],
                evidence_keys=["insulation_test_pass", "hipot_test_pass"],
            )
        )

    temperature = _number(values, "temperature_rise_c")
    if temperature is not None and temperature >= 55:
        findings.append(
            RuleFinding(
                code="HIGH_TEMPERATURE_RISE",
                title="温升异常",
                risk=RiskLevel.HIGH if temperature < 75 else RiskLevel.CRITICAL,
                observation=f"温升为 {temperature:.1f} C，高于演示阈值 55 C。",
                possible_causes=["摩擦或预紧过大", "相电流异常", "润滑不足", "装配偏心"],
                verification_steps=["停止连续耐久运行", "复核电流和摩擦力矩", "检查润滑与轴承装配"],
                evidence_keys=["temperature_rise_c"],
            )
        )

    vibration = _number(values, "vibration_rms_mm_s")
    if vibration is not None and vibration >= 4.5:
        findings.append(
            RuleFinding(
                code="VIBRATION_HIGH",
                title="振动偏高",
                risk=RiskLevel.HIGH if vibration >= 7.1 else RiskLevel.MEDIUM,
                observation=f"振动 RMS 为 {vibration:.2f} mm/s。",
                possible_causes=["转子或联轴器偏心", "轴承压装异常", "齿轮啮合异常", "紧固松动"],
                verification_steps=[
                    "按转速阶次检查频谱",
                    "复核同轴度和压装曲线",
                    "检查紧固扭矩与啮合印痕",
                ],
                evidence_keys=["vibration_rms_mm_s"],
            )
        )

    current = _number(values, "no_load_current_a")
    if current is not None and current >= 3.0:
        findings.append(
            RuleFinding(
                code="NO_LOAD_CURRENT_HIGH",
                title="空载电流偏高",
                risk=RiskLevel.MEDIUM,
                observation=f"空载电流为 {current:.2f} A。",
                possible_causes=["传动阻力过大", "电机相线或控制参数异常", "轴承预紧过大"],
                verification_steps=[
                    "分离电机与减速机构比较空载电流",
                    "检查三相电阻平衡",
                    "复核控制器参数版本",
                ],
                evidence_keys=["no_load_current_a"],
            )
        )

    torque = _number(values, "output_torque_nm")
    torque_min = _number(values, "output_torque_min_nm")
    if torque is not None and torque_min is not None and torque < torque_min:
        findings.append(
            RuleFinding(
                code="OUTPUT_TORQUE_LOW",
                title="输出扭矩不足",
                risk=RiskLevel.MEDIUM,
                observation=f"输出扭矩 {torque:.2f} Nm 低于下限 {torque_min:.2f} Nm。",
                possible_causes=[
                    "减速机构装配或啮合异常",
                    "电机输出不足",
                    "扭矩传感器标定漂移",
                    "润滑状态异常",
                ],
                verification_steps=[
                    "复核扭矩传感器零点与量程",
                    "对比电机侧电流和反电势",
                    "检查减速机构效率与装配记录",
                ],
                evidence_keys=["output_torque_nm", "output_torque_min_nm"],
            )
        )

    backlash = _number(values, "backlash_arcmin")
    backlash_max = _number(values, "backlash_max_arcmin")
    if backlash is not None and backlash_max is not None and backlash > backlash_max:
        findings.append(
            RuleFinding(
                code="BACKLASH_HIGH",
                title="反向间隙超限",
                risk=RiskLevel.MEDIUM,
                observation=f"反向间隙 {backlash:.2f} arcmin 高于上限 {backlash_max:.2f} arcmin。",
                possible_causes=[
                    "减速器装配偏差",
                    "预紧不足",
                    "齿面或滚动体尺寸异常",
                    "测量夹具松动",
                ],
                verification_steps=[
                    "先验证夹具重复性",
                    "复核选配分组和预紧记录",
                    "检查关键配合尺寸",
                ],
                evidence_keys=["backlash_arcmin", "backlash_max_arcmin"],
            )
        )

    position_error = _number(values, "position_error_deg")
    if position_error is not None and abs(position_error) >= 0.35:
        findings.append(
            RuleFinding(
                code="POSITION_ERROR_HIGH",
                title="位置误差偏高",
                risk=RiskLevel.MEDIUM,
                observation=f"位置误差为 {position_error:.3f} deg。",
                possible_causes=[
                    "编码器零位或安装偏差",
                    "磁环偏心",
                    "标定文件或固件版本不匹配",
                    "机械回差",
                ],
                verification_steps=[
                    "复核编码器原始值与零位标定",
                    "检查磁环跳动",
                    "确认固件和标定版本",
                    "交叉检查机械回差",
                ],
                evidence_keys=["position_error_deg"],
            )
        )

    return findings


def highest_risk(findings: Iterable[RuleFinding]) -> RiskLevel:
    rank = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
    return max((finding.risk for finding in findings), key=rank.get, default=RiskLevel.LOW)

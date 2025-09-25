import fetchData
import json
import contractInteraction
from custom_logger import get_logger

# 读取配置文件
with open("config/config.json", "r") as f:
    config = json.load(f)

logger = get_logger()

def select_vaults(all_vaults_data):

    min_remaining_hours = config["params"]["min_remaining_hours"]
    vaults_allocation = config["params"]["vaults_allocation"]

    all_vaults = all_vaults_data["vaults"]
    avg_incentives_rate = all_vaults_data["avgIncentivesRate"]

    # 读取 fixed_vaults
    selected_vaults_fixed = []
    fixed_vaults = config["fixed_vaults"]
    fixed_ids = {vault["id"] for vault in fixed_vaults}
    for vault in fixed_vaults:
        vault_id = vault["id"]
        for item in all_vaults:
            if item["id"] == vault_id:
                vault["incentivesRate"] = item["dynamicData"]["activeIncentivesRateUsd"]
                vault["remainingHours"] = item["dynamicData"]["remainingHours"]
                break
        selected_vaults_fixed.append(vault)

    # 读取 whitelisted_vaults
    selected_vaults = []
    whitelisted_vaults = config["whitelisted_vaults"]
    whitelisted_ids = {vault["id"] for vault in whitelisted_vaults}
    for vault in whitelisted_vaults:
        vault_id = vault["id"]
        for item in all_vaults:
            if item["id"] == vault_id:
                vault["incentivesRate"] = item["dynamicData"]["activeIncentivesRateUsd"]
                vault["remainingHours"] = item["dynamicData"]["remainingHours"]
                break

        if float(vault.get("incentivesRate", 0)) > avg_incentives_rate and float(vault.get("remainingHours", 0)) > min_remaining_hours:
            selected_vaults.append(vault)

    if len(selected_vaults) < len(vaults_allocation):
        for vault in all_vaults:
            vault_id = vault["id"]
            if vault_id in whitelisted_ids or vault_id in fixed_ids:
                continue
            if float(vault["dynamicData"]["remainingHours"]) > min_remaining_hours:
                selected_vaults.append({
                    "id": vault["id"],
                    "name": vault["metadata"]["name"] if vault.get("metadata") else vault["id"],
                    "incentivesRate": vault["dynamicData"]["activeIncentivesRateUsd"],
                    "remainingHours": vault["dynamicData"]["remainingHours"]
                })
                if len(selected_vaults) == len(vaults_allocation):
                    break

    selected_vaults = sorted(selected_vaults, key=lambda x: float(x["incentivesRate"]), reverse=True) 
    # 检查 selected_vaults_fixed 是否为空，如果为空则直接返回 selected_vaults
    if len(selected_vaults_fixed) == 0:
        selected_vaults = selected_vaults[:len(vaults_allocation)]
    else:
        selected_vaults = selected_vaults_fixed + selected_vaults[:(len(vaults_allocation) - len(selected_vaults_fixed))]

    return selected_vaults
                

def need_new_allocation(selected_vaults, current_vaults):
    number = 0
    for target_vault in selected_vaults:
        for current_vault in current_vaults:
            if target_vault["id"] == current_vault["id"] and target_vault["weights"] == current_vault["weights"]:
                number += 1
                break
    if number == len(selected_vaults):
        return False
    else:
        return True

def main():

    # 获取验证者公钥
    pubkey = config["validator_info"]["pubkey"]
    queued_reward_allocation = contractInteraction.get_queued_reward_allocation(pubkey)
    # if queued_reward_allocation["startBlock"] != 0 :
    #     logger.debug(f"当前分配已排队: {queued_reward_allocation}")
    #     return

    # 获取SNZ Validator 数据
    current_vaults = fetchData.get_validator_data()
    logger.debug(json.dumps(current_vaults, indent=4))
    # 获取所有Vault 数据
    all_vaults_data = fetchData.get_all_vaults()

    selected_vaults = select_vaults(all_vaults_data) 
    index = 0
    for vault in selected_vaults:
        vault["weights"] = config["params"]["vaults_allocation"][index]
        index += 1
    logger.debug(f"目标Vaults: {json.dumps(selected_vaults, indent=4)}")

    logger.debug(f"当前Vaults: {json.dumps(current_vaults, indent=4)}")

    current_block = contractInteraction.get_current_block()
    logger.info(f"当前区块: {current_block}")
    
    if not need_new_allocation(selected_vaults, current_vaults):
        logger.info("不需要新的BGT分配")
        return
    # 计算开始区块
    start_block = current_block + config["params"]["delay_blocks"]
    
    # 调用合约函数排队新的奖励分配
    logger.debug(f"开始区块: {start_block}")
    logger.debug(f"正在排队新的BGT分配...")
    tx_hash = contractInteraction.queue_new_reward_allocation(pubkey, start_block, selected_vaults)
    
    if tx_hash:
        logger.info(f"新BGT分配将在区块 {start_block} 开始生效")
        for vault in selected_vaults:
            logger.info(f"Vault: {vault['name']}, 权重: {vault['weights']}")
    else:
        logger.debug("BGT分配排队失败")


if __name__ == "__main__":
    main()

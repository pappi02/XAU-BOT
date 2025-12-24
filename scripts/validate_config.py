"""
Configuration validation module.
Checks critical settings at startup and logs warnings for potential issues.
"""

import logging
import os
from utils.symbol_helpers import resolve_symbol

logger = logging.getLogger(__name__)


def validate_config(config):
    """
    Validate critical configuration settings.
    
    Args:
        config: Config module with trading parameters
    
    Returns:
        dict: Validation results with 'valid' bool and 'issues' list
    """
    issues = []
    warnings = []
    
    # Critical checks (must pass)
    
    # 1. Symbol validation
    if not hasattr(config, 'SYMBOL') or not config.SYMBOL:
        issues.append("SYMBOL not set in config")
    else:
        canonical = resolve_symbol(config.SYMBOL)
        if config.SYMBOL != canonical:
            warnings.append(f"Symbol will be normalized from {config.SYMBOL} to {canonical}")
    
    # 2. Risk parameters
    if not hasattr(config, 'RISK_PER_TRADE_PCT'):
        issues.append("RISK_PER_TRADE_PCT not defined in config")
    else:
        risk = float(config.RISK_PER_TRADE_PCT)
        if risk < 0.001 or risk > 0.05:
            warnings.append(f"RISK_PER_TRADE_PCT {risk*100:.2f}% outside recommended range [0.1, 5]%")
    
    # 3. MT5 settings
    if not hasattr(config, 'MT5_ACCOUNT') or config.MT5_ACCOUNT is None:
        issues.append("MT5_ACCOUNT not set")
    if not hasattr(config, 'MT5_PASSWORD') or config.MT5_PASSWORD is None:
        issues.append("MT5_PASSWORD not set")
    if not hasattr(config, 'MT5_SERVER') or config.MT5_SERVER is None:
        issues.append("MT5_SERVER not set")
    
    # 4. Position limits
    if hasattr(config, 'MAX_CONCURRENT_POSITIONS'):
        max_pos = int(config.MAX_CONCURRENT_POSITIONS)
        if max_pos < 1 or max_pos > 50:
            warnings.append(f"MAX_CONCURRENT_POSITIONS {max_pos} outside typical range [1, 50]")
    
    # 5. RR parameters
    if hasattr(config, 'TP_RR_MIN') and hasattr(config, 'TP_RR_MAX'):
        rr_min = float(config.TP_RR_MIN)
        rr_max = float(config.TP_RR_MAX)
        if rr_min >= rr_max:
            issues.append(f"TP_RR_MIN ({rr_min}) must be less than TP_RR_MAX ({rr_max})")
        if rr_min < 0.5 or rr_max > 10:
            warnings.append(f"RR ratio range [{rr_min}, {rr_max}] outside typical [0.5, 10]")
    
    # 6. Lot sizing
    if hasattr(config, 'MIN_LOT_SIZE') and hasattr(config, 'MAX_LOT_SIZE'):
        min_lot = float(config.MIN_LOT_SIZE)
        max_lot = float(config.MAX_LOT_SIZE)
        if min_lot >= max_lot:
            issues.append(f"MIN_LOT_SIZE ({min_lot}) must be less than MAX_LOT_SIZE ({max_lot})")
    
    # 7. Scaling limits
    if hasattr(config, 'DYNAMIC_SCALING_EXPAND_LIMIT') and hasattr(config, 'MAX_CONCURRENT_POSITIONS'):
        expand = int(config.DYNAMIC_SCALING_EXPAND_LIMIT)
        max_pos = int(config.MAX_CONCURRENT_POSITIONS)
        if expand > max_pos:
            warnings.append(f"DYNAMIC_SCALING_EXPAND_LIMIT ({expand}) exceeds MAX_CONCURRENT_POSITIONS ({max_pos})")
    
    # 8. Daily loss limits
    if hasattr(config, 'BASE_MAX_DAILY_LOSS_PCT'):
        daily_loss = float(config.BASE_MAX_DAILY_LOSS_PCT)
        if daily_loss < 1 or daily_loss > 10:
            warnings.append(f"BASE_MAX_DAILY_LOSS_PCT {daily_loss}% outside typical range [1, 10]%")
    
    # 9. Account balance check
    if hasattr(config, 'MIN_ACCOUNT_BALANCE'):
        min_balance = float(config.MIN_ACCOUNT_BALANCE)
        if min_balance < 1:
            warnings.append(f"MIN_ACCOUNT_BALANCE {min_balance} very low; may cause trading issues")
    
    # Log results
    if issues:
        logger.error(f"❌ CONFIG VALIDATION FAILED: {len(issues)} critical issue(s)")
        for issue in issues:
            logger.error(f"   - {issue}")
    
    if warnings:
        logger.warning(f"⚠️  CONFIG WARNINGS: {len(warnings)} warning(s)")
        for warning in warnings:
            logger.warning(f"   - {warning}")
    
    if not issues and not warnings:
        logger.info("✅ CONFIG VALIDATION PASSED: All settings OK")
    
    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'warnings': warnings
    }


if __name__ == "__main__":
    # Test validation
    import config
    from logger_config import setup_logger
    
    setup_logger()
    result = validate_config(config)
    print(f"\nValidation result: {'PASS' if result['valid'] else 'FAIL'}")
    print(f"Issues: {len(result['issues'])}, Warnings: {len(result['warnings'])}")

# workflows/standard_recon_workflow.py
import logging
import autogen
from typing import Dict, List, Optional, Tuple, Union, Any

# Import specialized agents
from agents import (
    DomainIntelAgent,
    WebAppReconAgent, 
    NetworkReconAgent, 
    OSINTGatheringAgent,
    ReconReporter
)

# Import all tool functions
from tools import (
    dns_lookup,
    whois_lookup,
    get_http_headers,
    extract_security_headers,
    search_subdomains,
    scan_ports,
    search_google_dorks,
    detect_technologies,
    capture_website_screenshot,
    crawl_endpoints,
    analyze_ssl_tls,
    detect_waf,
    check_cors_config,
    detect_cms
)

# Import configuration
from config.settings import get_ag2_config_list

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("standard_recon_workflow")

def run_standard_recon_workflow(
    target_domain: str, 
    model_id: str = "gemini-2.5-pro-preview-05-06",
    output_format: str = "markdown",
    save_report: bool = True,
    save_raw_data: bool = True,
    tool_config: Optional[Dict[str, Any]] = None
) -> Tuple[str, Optional[str]]:
    """
    Run a standard reconnaissance workflow using specialized agents in sequence.
    
    Args:
        target_domain: The domain to perform reconnaissance on
        model_id: The model ID to use for LLM
        output_format: Format for the output report ("markdown", "html", "json")
        save_report: Whether to save the report to a file
        save_raw_data: Whether to save raw data to a file
        tool_config: Configuration for enabled tools and their parameters
        
    Returns:
        Tuple containing:
        - The reconnaissance report as a string
        - The path to the saved report file (if saved)
    """
    logger.info(f"Starting {tool_config.get('workflow_type', 'standard')} reconnaissance workflow for {target_domain}")
    
    # Set default tool config if not provided
    if tool_config is None:
        tool_config = {
            "enable_dns": True,
            "enable_whois": True,
            "enable_headers": True,
            "enable_subdomains": True,
            "enable_ports": True,
            "enable_osint": True,
            "enable_tech": True,
            "enable_screenshot": True,
            "enable_crawler": True,
            "enable_ssl_analysis": True,
            "enable_waf_detection": True,
            "enable_cors_checks": True,
            "enable_cms_detection": True,
            
            # Default tool parameters
            "port_list": None,
            "port_timeout": 1.0,
            "port_threads": 10,
            "port_scan_type": "tcp",
            
            "use_subdomain_apis": True,
            "max_subdomains": 100,
            
            "http_timeout": 10.0,
            "user_agent": None,
            
            "dorks_limit": 10,
            
            # Crawler parameters
            "crawler_depth": 1,
            "crawler_output_format": "json",
            "crawler_wordlist": True,
            "crawler_wayback": True,
            "crawler_analyze_js": True,
            "crawler_max_js": 10,
            "crawler_timeout": 10,
            
            # SSL/TLS analysis parameters
            "ssl_check_cert_info": True,
            "ssl_check_protocols": True,
            "ssl_check_ciphers": True,
            "ssl_timeout": 10,
            
            # WAF detection parameters
            "waf_test_payloads": True,
            "waf_timeout": 10,
            
            # CORS check parameters
            "cors_timeout": 10,
            
            # CMS detection parameters
            "cms_deep_scan": False,
            "cms_timeout": 10,
            
            "workflow_type": "standard"
        }
    
    # Adjust parameters based on workflow type
    if tool_config.get("workflow_type") == "quick":
        # Quick workflow - fewer ports, fewer subdomains, faster scans
        tool_config["port_timeout"] = min(tool_config.get("port_timeout", 1.0), 0.5)
        tool_config["max_subdomains"] = min(tool_config.get("max_subdomains", 100), 20)
        tool_config["dorks_limit"] = min(tool_config.get("dorks_limit", 10), 5)
        # Only scan common ports if not specified
        if not tool_config.get("port_list"):
            tool_config["port_list"] = [80, 443, 8080, 8443]
        # Quick crawling - less depth, fewer JS files
        tool_config["crawler_depth"] = min(tool_config.get("crawler_depth", 1), 1)
        tool_config["crawler_max_js"] = min(tool_config.get("crawler_max_js", 10), 5)
        tool_config["crawler_timeout"] = min(tool_config.get("crawler_timeout", 10), 5)
        # Quick SSL/WAF/CORS/CMS checks
        tool_config["ssl_check_ciphers"] = False
        tool_config["waf_test_payloads"] = False
        tool_config["cms_deep_scan"] = False
            
    elif tool_config.get("workflow_type") == "deep":
        # Deep workflow - more ports, more subdomains, more thorough scans
        tool_config["port_timeout"] = max(tool_config.get("port_timeout", 1.0), 2.0)
        tool_config["max_subdomains"] = max(tool_config.get("max_subdomains", 100), 200)
        tool_config["dorks_limit"] = max(tool_config.get("dorks_limit", 10), 20)
        tool_config["port_threads"] = max(tool_config.get("port_threads", 10), 20)
        # Deep crawling - more depth, more JS files, longer timeout
        tool_config["crawler_depth"] = max(tool_config.get("crawler_depth", 1), 2)
        tool_config["crawler_max_js"] = max(tool_config.get("crawler_max_js", 10), 20)
        tool_config["crawler_timeout"] = max(tool_config.get("crawler_timeout", 10), 15)
        # Thorough SSL/WAF/CORS/CMS checks
        tool_config["ssl_check_ciphers"] = True
        tool_config["waf_test_payloads"] = True
        tool_config["ssl_timeout"] = 15
        tool_config["waf_timeout"] = 15
        tool_config["cors_timeout"] = 15
        tool_config["cms_deep_scan"] = True
        tool_config["cms_timeout"] = 15
    
    # Initialize configuration
    config_list = get_ag2_config_list(model_id=model_id)
    llm_config = {
        "config_list": config_list,
        "cache_seed": 42,
        "temperature": 0.7,
    }
    
    # Initialize UserProxyAgent for tool execution
    tool_executor = autogen.UserProxyAgent(
        name="Tool_Executor_Proxy",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=1000,
        is_termination_msg=lambda x: isinstance(x, dict) and "TERMINATE" in x.get("content", "").upper(),
        code_execution_config={"use_docker": False},  # Disable Docker usage
        llm_config=False
    )
      # Register only the enabled tools with the UserProxyAgent
    function_map = {}
    if tool_config.get("enable_dns", True):
        function_map["dns_lookup"] = dns_lookup
        
    if tool_config.get("enable_whois", True):
        function_map["whois_lookup"] = whois_lookup
        
    if tool_config.get("enable_headers", True):
        function_map["get_http_headers"] = get_http_headers
        function_map["extract_security_headers"] = extract_security_headers
        
    if tool_config.get("enable_subdomains", True):
        function_map["search_subdomains"] = lambda domain: search_subdomains(
            domain=domain, 
            use_apis=tool_config.get("use_subdomain_apis", True),
            max_results=tool_config.get("max_subdomains", 100)
        )
        
    if tool_config.get("enable_ports", True):
        function_map["scan_ports"] = lambda target, ports=None: scan_ports(
            target=target,
            ports=ports if ports is not None else tool_config.get("port_list"),
            timeout=tool_config.get("port_timeout", 1.0),
            threads=tool_config.get("port_threads", 10),
            scan_type=tool_config.get("port_scan_type", "tcp")
        )
        
    if tool_config.get("enable_osint", True):
        function_map["search_google_dorks"] = lambda domain: search_google_dorks(
            domain=domain,
            max_results=tool_config.get("dorks_limit", 10)
        )
        
    if tool_config.get("enable_tech", True):
        function_map["detect_technologies"] = detect_technologies
        
    if tool_config.get("enable_screenshot", True):
        function_map["capture_website_screenshot"] = capture_website_screenshot
        
    # Add endpoint crawler to available functions
    if tool_config.get("enable_crawler", True):
        function_map["crawl_endpoints"] = lambda url: crawl_endpoints(
            url=url,
            depth=tool_config.get("crawler_depth", 1),
            output_format=tool_config.get("crawler_output_format", "json"),
            use_wordlist=tool_config.get("crawler_wordlist", True),
            use_wayback=tool_config.get("crawler_wayback", True),
            analyze_js=tool_config.get("crawler_analyze_js", True),
            max_js_files=tool_config.get("crawler_max_js", 10),
            timeout=tool_config.get("crawler_timeout", 10)
        )
    
    # Add SSL/TLS analyzer to available functions
    if tool_config.get("enable_ssl_analysis", True):
        function_map["analyze_ssl_tls"] = lambda url: analyze_ssl_tls(
            url=url,
            timeout=tool_config.get("ssl_timeout", 10),
            check_cert_info=tool_config.get("ssl_check_cert_info", True),
            check_protocols=tool_config.get("ssl_check_protocols", True),
            check_ciphers=tool_config.get("ssl_check_ciphers", True)
        )
    
    # Add WAF detector to available functions
    if tool_config.get("enable_waf_detection", True):
        function_map["detect_waf"] = lambda url: detect_waf(
            url=url,
            timeout=tool_config.get("waf_timeout", 10),
            user_agent=tool_config.get("user_agent"),
            test_payloads=tool_config.get("waf_test_payloads", True)
        )
    
    # Add CORS checker to available functions
    if tool_config.get("enable_cors_checks", True):
        function_map["check_cors_config"] = lambda url: check_cors_config(
            url=url,
            timeout=tool_config.get("cors_timeout", 10)
        )
    
    # Add CMS detector to available functions
    if tool_config.get("enable_cms_detection", True):
        function_map["detect_cms"] = lambda url: detect_cms(
            url=url,
            deep_scan=tool_config.get("cms_deep_scan", False),
            timeout=tool_config.get("cms_timeout", 10)
        )
    
    # Register the functions
    tool_executor.register_function(function_map=function_map)
    logger.info(f"Registered functions: {list(tool_executor.function_map.keys())}")
    
    # Initialize specialized agents
    domain_intel_agent = DomainIntelAgent(llm_config=llm_config)
    webapp_recon_agent = WebAppReconAgent(llm_config=llm_config)
    network_recon_agent = NetworkReconAgent(llm_config=llm_config)
    osint_gathering_agent = OSINTGatheringAgent(llm_config=llm_config)
    
    # Initialize the report generator
    reporter = ReconReporter(llm_config=llm_config)
    
    # Dictionary to store collected data summaries
    collected_data = {
        "target_domain": target_domain,
        "summaries": {},
        "findings": []
    }
    
    # Step 1: Domain Intelligence (DNS & WHOIS)
    if tool_config.get("enable_dns", True) or tool_config.get("enable_whois", True):
        logger.info("Step 1: Collecting domain intelligence (DNS & WHOIS)")
        
        # Adjust the prompt based on which tools are enabled
        domain_tools = []
        if tool_config.get("enable_dns", True):
            domain_tools.append("DNS records")
        if tool_config.get("enable_whois", True):
            domain_tools.append("WHOIS information")
            
        domain_intel_prompt = f"Collect {' and '.join(domain_tools)} for the domain: {target_domain}"
        domain_intel_chat = tool_executor.initiate_chat(
            domain_intel_agent,
            message=domain_intel_prompt
        )
        
        # Get the last message from the chat
        try:
            collected_data["summaries"]["domain_intel"] = domain_intel_agent.last_message(tool_executor)["content"]
        except (ValueError, KeyError, AttributeError, TypeError):
            if hasattr(domain_intel_chat, 'messages') and domain_intel_chat.messages:
                collected_data["summaries"]["domain_intel"] = domain_intel_chat.messages[-1]["content"]
            elif hasattr(domain_intel_chat, 'get_last_message'):
                collected_data["summaries"]["domain_intel"] = domain_intel_chat.get_last_message()["content"]
            elif hasattr(domain_intel_chat, 'chat_history') and domain_intel_chat.chat_history:
                collected_data["summaries"]["domain_intel"] = domain_intel_chat.chat_history[-1]["content"]
            else:
                collected_data["summaries"]["domain_intel"] = "Failed to retrieve chat summary"
                
        logger.info("Domain intelligence collection completed")
    
    # Step 2: Web Application Reconnaissance
    web_tools_enabled = any([
        tool_config.get("enable_headers", True),
        tool_config.get("enable_subdomains", True),
        tool_config.get("enable_tech", True),
        tool_config.get("enable_screenshot", True),
        tool_config.get("enable_crawler", True),
        tool_config.get("enable_ssl_analysis", True),
        tool_config.get("enable_waf_detection", True),
        tool_config.get("enable_cors_checks", True),
        tool_config.get("enable_cms_detection", True)
    ])
    
    if web_tools_enabled:
        logger.info("Step 2: Performing web application reconnaissance")
        
        # Build the prompt based on which tools are enabled
        web_tools = []
        if tool_config.get("enable_headers", True):
            web_tools.append("HTTP headers and security headers")
        if tool_config.get("enable_tech", True):
            web_tools.append("technologies")
        if tool_config.get("enable_subdomains", True):
            web_tools.append("subdomains")
        if tool_config.get("enable_screenshot", True):
            web_tools.append("screenshot of the website")
        if tool_config.get("enable_crawler", True):
            web_tools.append("website endpoints")
        if tool_config.get("enable_ssl_analysis", True):
            web_tools.append("SSL/TLS security configuration")
        if tool_config.get("enable_waf_detection", True):
            web_tools.append("web application firewall (WAF) details")
        if tool_config.get("enable_cors_checks", True):
            web_tools.append("CORS configuration security")
        if tool_config.get("enable_cms_detection", True):
            web_tools.append("content management system (CMS) information")
            
        webapp_recon_prompt = f"Gather {', '.join(web_tools)} for the website: {target_domain}"
        webapp_recon_chat = tool_executor.initiate_chat(
            webapp_recon_agent,
            message=webapp_recon_prompt
        )
        
        # Get the last message from the chat
        try:
            collected_data["summaries"]["webapp_recon"] = webapp_recon_agent.last_message(tool_executor)["content"]
        except (ValueError, KeyError, AttributeError, TypeError):
            if hasattr(webapp_recon_chat, 'messages') and webapp_recon_chat.messages:
                collected_data["summaries"]["webapp_recon"] = webapp_recon_chat.messages[-1]["content"]
            elif hasattr(webapp_recon_chat, 'get_last_message'):
                collected_data["summaries"]["webapp_recon"] = webapp_recon_chat.get_last_message()["content"]
            elif hasattr(webapp_recon_chat, 'chat_history') and webapp_recon_chat.chat_history:
                collected_data["summaries"]["webapp_recon"] = webapp_recon_chat.chat_history[-1]["content"]
            else:
                collected_data["summaries"]["webapp_recon"] = "Failed to retrieve web application reconnaissance summary"
                
        logger.info("Web application reconnaissance completed")
    
    # Step 3: Network Reconnaissance (Port Scanning)
    if tool_config.get("enable_ports", True):
        logger.info("Step 3: Performing network reconnaissance (port scanning)")
        
        # Build the prompt with information about the scan configuration
        port_info = ""
        if tool_config.get("port_list"):
            port_info = f" on specific ports: {tool_config.get('port_list')}"
        scan_type_info = f" using {tool_config.get('port_scan_type', 'TCP').upper()} scanning"
        
        network_recon_prompt = f"Scan for open ports{port_info} on the domain: {target_domain}{scan_type_info}"
        network_recon_chat = tool_executor.initiate_chat(
            network_recon_agent,
            message=network_recon_prompt
        )
        
        # Get the last message from the chat
        try:
            collected_data["summaries"]["network_recon"] = network_recon_agent.last_message(tool_executor)["content"]
        except (ValueError, KeyError, AttributeError, TypeError):
            if hasattr(network_recon_chat, 'messages') and network_recon_chat.messages:
                collected_data["summaries"]["network_recon"] = network_recon_chat.messages[-1]["content"]
            elif hasattr(network_recon_chat, 'get_last_message'):
                collected_data["summaries"]["network_recon"] = network_recon_chat.get_last_message()["content"]
            elif hasattr(network_recon_chat, 'chat_history') and network_recon_chat.chat_history:
                collected_data["summaries"]["network_recon"] = network_recon_chat.chat_history[-1]["content"]
            else:
                collected_data["summaries"]["network_recon"] = "Failed to retrieve network reconnaissance summary"
                
        logger.info("Network reconnaissance completed")
    
    # Step 4: OSINT Gathering (Google Dorking)
    if tool_config.get("enable_osint", True):
        logger.info("Step 4: Gathering OSINT information using Google Dorking")
        
        osint_prompt = f"Perform Google dorking on the domain: {target_domain} with a limit of {tool_config.get('dorks_limit', 10)} results"
        osint_chat = tool_executor.initiate_chat(
            osint_gathering_agent,
            message=osint_prompt
        )
        
        # Get the last message from the chat
        try:
            collected_data["summaries"]["osint_gathering"] = osint_gathering_agent.last_message(tool_executor)["content"]
        except (ValueError, KeyError, AttributeError, TypeError):
            if hasattr(osint_chat, 'messages') and osint_chat.messages:
                collected_data["summaries"]["osint_gathering"] = osint_chat.messages[-1]["content"]
            elif hasattr(osint_chat, 'get_last_message'):
                collected_data["summaries"]["osint_gathering"] = osint_chat.get_last_message()["content"]
            elif hasattr(osint_chat, 'chat_history') and osint_chat.chat_history:
                collected_data["summaries"]["osint_gathering"] = osint_chat.chat_history[-1]["content"]
            else:
                collected_data["summaries"]["osint_gathering"] = "Failed to retrieve OSINT gathering summary"
                
        logger.info("OSINT gathering completed")
    
    # Generate the final report
    logger.info("Generating final reconnaissance report")
    report, report_path = reporter.generate_report(
        target_domain=target_domain, 
        collected_data=collected_data,
        output_format=output_format,
        save_report=save_report,
        save_raw_data=save_raw_data
    )
    
    # Print report location
    if report_path:
        logger.info(f"Report saved to: {report_path}")
    
    logger.info("Reconnaissance workflow completed successfully")
    
    return report, report_path

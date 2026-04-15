# mock 实现

def main():
    """主函数"""
    args = parse_args()
    
    # 初始化args，用于测试
    args.ne_id = "12345678-1234-1234-1234-123456789999"
    args.service_port_index = 0
    args.policy_profile = "defaultProfile"
    args.onu_res_id = "12345678-1234-1234-1234-123456789999"
    args.app_id = "12345678-1234-1234-1234-123456789999"

    if args.business_type != "experience-assurance":
        args.application_type = None
        args.application = None

    print("=" * 60)
    print("体验保障配置接口调用工具")
    print("=" * 60)

    # 处理输入参数
    base_url, csrf_token, cookie, ne_id, service_port_index, policy_profile, onu_res_id, app_id = process_input_args(args)

    # 判断是否已有有效的token和cookie
    from NCELogin import NCELogin
    nce_login = NCELogin(config_file=args.config)
    
    # 检查token是否过期
    if csrf_token and cookie and not nce_login.is_token_expired(config_file=args.config):
        # token未过期，直接使用配置文件中的token和cookie
        print(f"\n[2] 使用配置文件中的认证信息...")
        client = ExperienceAssuranceClient(
            base_url=base_url,
            csrf_token=csrf_token,
            cookie=cookie
        )
    else:
        # 需要通过NCELogin获取认证
        print(f"\n[2] 正在登录获取认证信息...")
        success = nce_login.get_cookie_and_token()

        if not success:
            print("登录失败，无法继续调用接口")
            exit(1)

        client = ExperienceAssuranceClient(
            base_url=base_url,
            nce_login=nce_login
        )

    # 调用接口
    print(f"\n[3] 正在创建体验保障配置任务...")

    try:
        result = client.create_assure_config_task(
            ne_id=ne_id,
            service_port_index=service_port_index,
            policy_profile=policy_profile,
            onu_res_id=onu_res_id,
            app_id=app_id
        )

        result = client.query_assure_config_task(
            ne_ip="200.30.33.63",
            fsp="0/3/2",
            onu_id="5",
            args=args
        )

        # 将结果输出为JSON文件
        output_path = r'../output_dir'
        output_file = os.path.join(output_path, "experience_assurance_output.json")
        os.makedirs(output_path, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {output_file}")

    except Exception as e:
        print(f"\n调用失败: {e}")
        print("=" * 60)
        exit(1)

if __name__ == "__main__":
    main()
